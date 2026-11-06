// 관리자 첨부파일 조회를 흉내 내는 모의 서버. 조회 전용이고 저장소 키·경로는 내보내지 않는다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, denyUnless } from './auth';

type File = Schemas['AdminFile'];

const fid = (n: number) => `31${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;

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

/** 시험 사이에 파일을 처음 상태로 되돌린다. */
export function resetMockFiles(): void {
  rows = initialState();
}

const summary = (f: File): Schemas['AdminFileSummary'] => ({ fileId: f.fileId, fileName: f.fileName, ownerKind: f.ownerKind, ownerLabel: f.ownerLabel, sizeBytes: f.sizeBytes, status: f.status, registeredOn: f.registeredOn });

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
];