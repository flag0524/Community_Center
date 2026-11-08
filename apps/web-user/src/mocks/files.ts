// 회원 첨부를 흉내 내는 모의 서버. 자기 지원서·문의에만 올리고 제거하며 검사는 목록을 두 번 읽어야 끝난다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, csrfRejected, currentMockMember } from './auth';

type MyFile = Schemas['MyFile'];

export const UPLOAD_LIMITS = { maxFiles: 10, maxBytes: 20 * 1024 * 1024, allowedExtensions: ['pdf', 'hwp', 'hwpx', 'docx', 'xlsx', 'jpg', 'png'] };
const fid = (n: number) => `32${String(n).padStart(20, '0')}`;
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());

// 다른 모의 서버가 자기 업무에서 이 회원의 것인지와 잠겼는지를 알려 준다. 남의 업무는 null이다.
export interface OwnerInfo {
  locked: boolean;
}
const providers: Record<string, (ownerId: string, memberId: string) => OwnerInfo | null> = {};
export const registerOwnerInfo = (group: string, provider: (ownerId: string, memberId: string) => OwnerInfo | null): void => {
  providers[group] = provider;
};

interface Entry {
  file: MyFile;
  ownerPath: string;
  memberId: string;
  reads: number;
}
let entries: Entry[] = [];
let seq = 0;
let idempotent = new Map<string, MyFile>();

/** 시험 사이에 올린 파일을 비운다. */
export function resetMockFiles(): void {
  entries = [];
  seq = 0;
  idempotent = new Map();
}

export type UploadResult = { file: MyFile } | { status: number; code: 'NOT_FOUND' | 'RULE_REJECTED' | 'CONFLICT_STATE'; fields?: Record<string, string> };

const groupOf = (ownerPath: string) => ownerPath.split('/')[2] ?? '';
const ownerIdOf = (ownerPath: string) => ownerPath.split('/')[3] ?? '';
const infoOf = (ownerPath: string, memberId: string) => providers[groupOf(ownerPath)]?.(ownerIdOf(ownerPath), memberId) ?? null;
const live = (ownerPath: string) => entries.filter((entry) => entry.ownerPath === ownerPath && entry.file.status !== 'DELETE');

/** 올린 파일을 받아 검사 대기로 저장한다. 확장자·크기·개수는 서버가 최종 판정한다. */
export function receiveUpload(ownerPath: string, memberId: string, input: { name: string; size: number }): UploadResult {
  const info = infoOf(ownerPath, memberId);
  if (!info) return { status: 404, code: 'NOT_FOUND' };
  if (info.locked) return { status: 409, code: 'CONFLICT_STATE' };
  const extension = input.name.includes('.') ? input.name.split('.').pop()!.toLowerCase() : '';
  const fail = (file: string): UploadResult => ({ status: 422, code: 'RULE_REJECTED', fields: { file } });
  if ([...input.name.normalize('NFC')].length > 128) return fail('파일 이름은 128자를 넘을 수 없습니다.');
  if (!UPLOAD_LIMITS.allowedExtensions.includes(extension)) return fail(`허용되지 않는 형식입니다. (${UPLOAD_LIMITS.allowedExtensions.join(', ')})`);
  if (input.size === 0) return fail('빈 파일은 올릴 수 없습니다.');
  if (input.size > UPLOAD_LIMITS.maxBytes) return fail('파일은 20MB 이하만 올릴 수 있습니다.');
  if (live(ownerPath).length >= UPLOAD_LIMITS.maxFiles) return fail(`파일은 ${UPLOAD_LIMITS.maxFiles}개까지 올릴 수 있습니다.`);
  seq += 1;
  const file: MyFile = { fileId: fid(seq), fileName: input.name, sizeBytes: input.size, status: 'PENDING', registeredOn: today(), blockReason: null };
  entries.push({ file, ownerPath, memberId, reads: 0 });
  return { file };
}

// 워커가 검사를 끝낸 것처럼 검사 대기 파일을 정한다. 이름에 virus가 들어 있으면 차단한다.
function scan(ownerPath: string): void {
  for (const entry of live(ownerPath)) {
    entry.reads += 1;
    if (entry.file.status !== 'PENDING' || entry.reads < 2) continue;
    if (entry.file.fileName.toLowerCase().includes('virus')) Object.assign(entry.file, { status: 'BLOCK', blockReason: '악성코드가 의심됩니다.' });
    else entry.file.status = 'SAFE';
  }
}

const OWNER_ROUTES = ['instructor-applications', 'inquiries', 'reduction-reviews'] as const;

/** 소유 업무 경로에 남아 있는 파일 수. */
export const countFiles = (ownerPath: string): number => live(ownerPath).length;

/** 시험·시연용으로 이미 검사를 통과한 파일을 소유 업무에 붙여 둔다. */
export function seedFile(ownerPath: string, memberId: string, fileName: string, sizeBytes = 245_760): void {
  seq += 1;
  entries.push({ file: { fileId: fid(seq), fileName, sizeBytes, status: 'SAFE', registeredOn: today(), blockReason: null }, ownerPath, memberId, reads: 99 });
}

export const fileHandlers = [
  http.delete('/api/v1/me/files/:fileId', ({ request, params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const entry = entries.find((item) => item.file.fileId === params.fileId);
    if (!entry || entry.memberId !== member.memberId || entry.file.status === 'DELETE') return apiError('NOT_FOUND');
    if (infoOf(entry.ownerPath, member.memberId)?.locked) return apiError('CONFLICT_STATE');
    entry.file.status = 'DELETE';
    return new HttpResponse(null, { status: 204 });
  }),

  http.get('/api/v1/me/files/:fileId', ({ params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const entry = entries.find((item) => item.file.fileId === params.fileId);
    if (!entry || entry.memberId !== member.memberId || entry.file.status !== 'SAFE') return apiError('NOT_FOUND');
    return new HttpResponse('시험용 첨부 내용입니다.', {
      headers: {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(entry.file.fileName)}`,
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'private, no-store',
      },
    });
  }),

  ...OWNER_ROUTES.flatMap((group) => [
    http.get(`/api/v1/me/${group}/:ownerId/files`, ({ params }) => {
      const member = currentMockMember();
      if (!member) return apiError('UNAUTHENTICATED');
      const ownerPath = `/me/${group}/${String(params.ownerId)}`;
      const info = infoOf(ownerPath, member.memberId);
      if (!info) return apiError('NOT_FOUND');
      scan(ownerPath);
      return HttpResponse.json({ items: live(ownerPath).map((entry) => entry.file), canEdit: !info.locked, ...UPLOAD_LIMITS } satisfies Schemas['MyFileList']);
    }),

    http.post(`/api/v1/me/${group}/:ownerId/files`, async ({ request, params }) => {
      const member = currentMockMember();
      if (!member) return apiError('UNAUTHENTICATED');
      if (csrfRejected(request)) return apiError('FORBIDDEN');
      const key = request.headers.get('Idempotency-Key');
      if (!key) return apiError('VALIDATION_FAILED', { 'Idempotency-Key': '멱등키가 필요합니다.' });
      const known = idempotent.get(key);
      if (known) return HttpResponse.json(known, { status: 201 });
      const file = (await request.formData()).get('file');
      if (!(file instanceof Blob)) return apiError('RULE_REJECTED', { file: '파일을 선택해 주세요.' });
      const result = receiveUpload(`/me/${group}/${String(params.ownerId)}`, member.memberId, { name: (file as { name?: string }).name ?? '', size: file.size });
      if ('file' in result) {
        idempotent.set(key, result.file);
        return HttpResponse.json(result.file, { status: 201 });
      }
      return apiError(result.code, result.fields);
    }),
  ]),
];