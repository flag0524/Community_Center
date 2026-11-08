// 관리자 첨부파일을 흉내 내는 모의 서버. 소유 업무 경로로 올리고 제거하며 저장소 키·경로는 내보내지 않는다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, denyCsrf, denyUnless } from './auth';
import { mockPostTitle } from './boards';
import { mockContentInfo } from './contents';
import { mockCourseName } from './education';

type File = Schemas['AdminFile'];

const fid = (n: number) => `31${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());

export const UPLOAD_LIMITS = { maxFiles: 10, maxBytes: 20 * 1024 * 1024, allowedExtensions: ['pdf', 'hwp', 'hwpx', 'docx', 'xlsx', 'jpg', 'png'] };
const limitsOf = (group: string) => ({ ...UPLOAD_LIMITS, ...OWNERS[group]?.limits });
const MIME: Record<string, string> = {
  pdf: 'application/pdf',
  hwp: 'application/x-hwp',
  hwpx: 'application/hwp+zip',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  jpg: 'image/jpeg',
  png: 'image/png',
};
// 소유 업무마다 올릴 때 필요한 권한, 소유 업무의 이름, 잠겼는지를 정한다. 환불·강사 지원은 해당 모의 서버가 정보를 등록한다.
export interface OwnerInfo {
  label: string;
  locked: boolean;
  /** 이 소유 업무가 파일을 받지 않을 때의 이유. 올리기를 거절한다. */
  reject?: string;
}
type Authority = Schemas['AdminAuthority'];
const registered: Record<string, (ownerId: string) => OwnerInfo | null> = {};
/** 다른 모의 서버가 자기 업무의 이름과 잠금 상태를 첨부 모의 서버에 알린다. */
export const registerOwnerInfo = (group: string, provider: (ownerId: string) => OwnerInfo | null): void => {
  registered[group] = provider;
};
const IMAGE_TYPES: Array<Schemas['ContentType']> = ['VISUAL', 'BANNER', 'POPUP'];
interface OwnerConfig {
  kind: Schemas['FileOwnerKind'];
  purpose: Schemas['FilePurpose'];
  authority: Authority;
  info: (ownerId: string) => OwnerInfo | null;
  /** 이 소유 업무만의 한도. 없으면 공통 한도를 쓴다. */
  limits?: Partial<typeof UPLOAD_LIMITS>;
}
const OWNERS: Record<string, OwnerConfig> = {
  posts: { kind: 'POST', purpose: 'ATTACH', authority: 'AU.POST_W', info: (id) => (mockPostTitle(id) ? { label: mockPostTitle(id), locked: false } : null) },
  courses: { kind: 'COURSE', purpose: 'PLAN', authority: 'AU.CORS_W', info: (id) => (mockCourseName(id) ? { label: mockCourseName(id), locked: false } : null) },
  // 홈 이미지는 비주얼·배너·팝업만, jpg·png 한 장이다(첨부 설계 6절, 가정).
  contents: {
    kind: 'CONTENT',
    purpose: 'IMAGE',
    authority: 'AU.SITE_W',
    limits: { maxFiles: 1, allowedExtensions: ['jpg', 'png'] },
    info: (id) => {
      const content = mockContentInfo(id);
      if (!content) return null;
      const usesImage = IMAGE_TYPES.includes(content.contentType);
      return { label: content.title, locked: !usesImage, reject: usesImage ? undefined : '이 유형은 이미지를 쓰지 않습니다.' };
    },
  },
  refunds: { kind: 'REFUND', purpose: 'PROOF', authority: 'AU.RFND_A', info: (id) => registered.refunds?.(id) ?? null },
  'instructor-applications': { kind: 'INSTRUCTOR_APPLICATION', purpose: 'PROOF', authority: 'AU.INSTR_W', info: (id) => registered['instructor-applications']?.(id) ?? null },
};

// 파일을 직접 소유한 다른 모의 서버(감면 증빙)가 내려받기를 맡길 수 있게 한다.
export interface ExternalFile {
  authority: Authority;
  status: Schemas['FileStatus'];
  fileName: string;
  onDownload: (by: string) => void;
}
const resolvers: Array<(fileId: string) => ExternalFile | undefined> = [];
export const registerFileResolver = (resolver: (fileId: string) => ExternalFile | undefined): void => {
  resolvers.push(resolver);
};

/** 소유 업무 경로에 지워지지 않고 남아 있는 파일 수. */
export const countOwnerFiles = (ownerPath: string): number =>
  owned.filter((item) => item.ownerPath === ownerPath && rows.find((row) => row.fileId === item.fileId)?.status !== 'DELETE').length;
function initialState(): File[] {
  const row = (n: number, fileName: string, ownerKind: Schemas['FileOwnerKind'], ownerLabel: string, status: Schemas['FileStatus'], extra: Partial<File> = {}): File => ({
    fileId: fid(n), fileName, ownerKind, ownerLabel, sizeBytes: 245_760, status, registeredOn: '2026-10-20', purpose: 'ATTACH', mimeType: 'application/pdf', hashPrefix: 'a3f9c2d1', blockReason: null,
    downloads: [], ...extra,
  });
  return [
    row(1, '4분기 수강 안내.pdf', 'POST', '4분기 수강 접수 안내', 'SAFE', { registeredOn: '2026-10-28', downloads: [{ at: '2026-10-29T10:12:00+09:00', by: '김○○', byAdmin: false }, { at: '2026-10-30T09:01:00+09:00', by: '김관리', byAdmin: true }] }),
    row(2, '요가 강의계획서.pdf', 'COURSE', '요가 기초반', 'SAFE', { purpose: 'PLAN', registeredOn: '2026-10-10', sizeBytes: 1_048_576 }),
    row(3, '자격증 사본.jpg', 'INSTRUCTOR_APPLICATION', '박○○ 강사 지원', 'SAFE', { purpose: 'PROOF', mimeType: 'image/jpeg', sizeBytes: 802_816, registeredOn: '2026-10-05' }),
    row(4, '의심 파일.exe', 'POST', '자료실 게시물', 'BLOCK', { mimeType: 'application/octet-stream', sizeBytes: 9_437_184, registeredOn: '2026-10-25', blockReason: '실행 파일은 올릴 수 없는 형식입니다.' }),
    row(5, '휴관 안내 이미지.png', 'CONTENT', '휴관일 안내 팝업', 'PENDING', { purpose: 'IMAGE', mimeType: 'image/png', sizeBytes: 512_000, registeredOn: '2026-11-05' }),
    row(6, '환불 증빙.pdf', 'REFUND', '환불 요청', 'SAFE', { purpose: 'PROOF', registeredOn: '2026-10-18' }),
  ];
}

let rows = initialState();
// 소유 업무 경로로 올린 파일. 검사는 워커가 하므로 목록을 두 번 읽어야 검사 대기에서 벗어난다.
let owned: Array<{ fileId: string; ownerPath: string; reads: number }> = [];
let uploadSeq = 100;
let idempotent = new Map<string, Schemas['OwnerFile']>();

/** 시험 사이에 파일을 처음 상태로 되돌린다. */
export function resetMockFiles(): void {
  rows = initialState();
  owned = [];
  uploadSeq = 100;
  idempotent = new Map();
}

const summary = (f: File): Schemas['AdminFileSummary'] => ({ fileId: f.fileId, fileName: f.fileName, ownerKind: f.ownerKind, ownerLabel: f.ownerLabel, sizeBytes: f.sizeBytes, status: f.status, registeredOn: f.registeredOn });
const ownerFile = (row: File): Schemas['OwnerFile'] => ({ fileId: row.fileId, fileName: row.fileName, sizeBytes: row.sizeBytes, status: row.status, registeredOn: row.registeredOn, blockReason: row.blockReason });

// 워커가 검사를 끝낸 것처럼 검사 대기 파일을 정한다. 이름에 virus가 들어 있으면 차단한다.
function scan(ownerPath: string): void {
  for (const item of owned.filter((entry) => entry.ownerPath === ownerPath)) {
    item.reads += 1;
    const row = rows.find((entry) => entry.fileId === item.fileId);
    if (row?.status === 'PENDING' && item.reads >= 2) {
      if (row.fileName.toLowerCase().includes('virus')) Object.assign(row, { status: 'BLOCK', blockReason: '악성코드가 의심됩니다.' });
      else row.status = 'SAFE';
    }
  }
}

export type UploadResult = { file: Schemas['OwnerFile'] } | { status: number; code: 'NOT_FOUND' | 'RULE_REJECTED' | 'CONFLICT_STATE'; fields?: Record<string, string> };

/** 올린 파일을 받아 검사 대기로 저장한다. 확장자·크기·개수는 서버가 최종 판정한다. */
export function receiveUpload(ownerPath: string, input: { name: string; size: number }): UploadResult {
  const [, group, ownerId] = ownerPath.split('/');
  const owner = OWNERS[group ?? ''];
  const info = owner?.info(ownerId ?? '');
  if (!owner || !info) return { status: 404, code: 'NOT_FOUND' };
  const limits = limitsOf(group ?? '');
  const reject = (message: string): UploadResult => ({ status: 422, code: 'RULE_REJECTED', fields: { file: message } });
  if (info.reject) return reject(info.reject);
  if (info.locked) return { status: 409, code: 'CONFLICT_STATE' };
  const extension = input.name.includes('.') ? input.name.split('.').pop()!.toLowerCase() : '';
  const fail = (file: string): UploadResult => ({ status: 422, code: 'RULE_REJECTED', fields: { file } });
  if ([...input.name.normalize('NFC')].length > 128) return fail('파일 이름은 128자를 넘을 수 없습니다.');
  if (!limits.allowedExtensions.includes(extension)) return fail(`허용되지 않는 형식입니다. (${limits.allowedExtensions.join(', ')})`);
  if (input.size === 0) return fail('빈 파일은 올릴 수 없습니다.');
  if (input.size > UPLOAD_LIMITS.maxBytes) return fail('파일은 20MB 이하만 올릴 수 있습니다.');
  if (countOwnerFiles(ownerPath) >= limits.maxFiles) return fail(`파일은 ${limits.maxFiles}개까지 올릴 수 있습니다.`);
  uploadSeq += 1;
  const row: File = {
    fileId: fid(uploadSeq), fileName: input.name, ownerKind: owner.kind, ownerLabel: info.label, sizeBytes: input.size, status: 'PENDING', registeredOn: today(), purpose: owner.purpose,
    mimeType: MIME[extension] ?? 'application/octet-stream', hashPrefix: 'f00dcafe', blockReason: null, downloads: [],
  };
  rows.push(row);
  owned.push({ fileId: row.fileId, ownerPath, reads: 0 });
  return { file: ownerFile(row) };
}

export const fileHandlers = [
  http.get('/api/admin/v1/files', ({ request }) => {
    const denied = denyUnless('AU.POST_W', 'AU.SITE_W');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const owner = params.get('ownerKind');
    const status = params.get('status');
    const q = params.get('q')?.trim();
    const list = rows
      .filter((row) => (!owner || row.ownerKind === owner) && (!status || row.status === status) && (!q || row.fileName.includes(q)))
      .sort((a, b) => b.registeredOn.localeCompare(a.registeredOn) || b.fileId.localeCompare(a.fileId));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: list.slice((page - 1) * size, page * size).map(summary), page, size, total: list.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.get('/api/admin/v1/files/:fileId', ({ params }) => {
    const denied = denyUnless('AU.POST_W', 'AU.SITE_W');
    if (denied) return denied;
    const row = rows.find((item) => item.fileId === params.fileId);
    return row ? HttpResponse.json(row) : apiError('NOT_FOUND');
  }),

  http.get('/api/admin/v1/files/:fileId/download', ({ params }) => {
    const fileId = String(params.fileId);
    const external = resolvers.map((resolve) => resolve(fileId)).find((item) => item !== undefined);
    const entry = owned.find((item) => item.fileId === fileId);
    const row = rows.find((item) => item.fileId === fileId);
    const group = entry?.ownerPath.split('/')[1] ?? '';
    const authority: Authority[] = external ? [external.authority] : entry ? [OWNERS[group]!.authority] : ['AU.POST_W', 'AU.SITE_W'];
    const denied = denyUnless(...authority, ...(group === 'courses' ? (['AU.CORS_R'] as const) : []));
    if (denied) return denied;
    const status = external?.status ?? row?.status;
    const fileName = external?.fileName ?? row?.fileName;
    if (!fileName || status !== 'SAFE') return apiError('NOT_FOUND');
    if (external) external.onDownload(currentAdminName());
    else row!.downloads.push({ at: new Date().toISOString(), by: currentAdminName(), byAdmin: true });
    return new HttpResponse('시험용 첨부 내용입니다.', {
      headers: {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(fileName)}`,
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'private, no-store',
      },
    });
  }),
  http.delete('/api/admin/v1/files/:fileId', ({ request, params }) => {
    const entry = owned.find((item) => item.fileId === params.fileId);
    const [, group, ownerId] = entry?.ownerPath.split('/') ?? [];
    const denied = denyCsrf(request) ?? denyUnless(group ? OWNERS[group]!.authority : 'AU.POST_W');
    if (denied) return denied;
    const row = rows.find((item) => item.fileId === params.fileId);
    if (!entry || !row || row.status === 'DELETE') return apiError('NOT_FOUND');
    if (OWNERS[group ?? '']?.info(ownerId ?? '')?.locked) return apiError('CONFLICT_STATE');
    row.status = 'DELETE';
    return new HttpResponse(null, { status: 204 });
  }),

  ...Object.entries(OWNERS).flatMap(([group, owner]) => [
    http.get(`/api/admin/v1/${group}/:ownerId/files`, ({ params }) => {
      const denied = denyUnless(owner.authority, ...(group === 'courses' ? (['AU.CORS_R'] as const) : []));
      if (denied) return denied;
      const ownerPath = `/${group}/${String(params.ownerId)}`;
      const info = owner.info(String(params.ownerId));
      if (!info) return apiError('NOT_FOUND');
      scan(ownerPath);
      const items = owned
        .filter((item) => item.ownerPath === ownerPath)
        .map((item) => rows.find((row) => row.fileId === item.fileId)!)
        .filter((row) => row.status !== 'DELETE')
        .map(ownerFile);
      return HttpResponse.json({ items, canEdit: !info.locked, ...limitsOf(group) } satisfies Schemas['OwnerFileList']);
    }),

    http.post(`/api/admin/v1/${group}/:ownerId/files`, async ({ request, params }) => {
      const denied = denyCsrf(request) ?? denyUnless(owner.authority);
      if (denied) return denied;
      const key = request.headers.get('Idempotency-Key');
      const found = key ? idempotent.get(key) : undefined;
      if (found) return HttpResponse.json(found, { status: 201 });
      const file = (await request.formData()).get('file');
      if (!(file instanceof Blob)) return apiError('RULE_REJECTED', { file: '파일을 선택해 주세요.' });
      const result = receiveUpload(`/${group}/${String(params.ownerId)}`, { name: (file as { name?: string }).name ?? '', size: file.size });
      if ('file' in result) {
        if (key) idempotent.set(key, result.file);
        return HttpResponse.json(result.file, { status: 201 });
      }
      return apiError(result.code, result.fields);
    }),
  ]),
];