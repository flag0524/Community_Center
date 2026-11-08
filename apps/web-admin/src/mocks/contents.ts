// 관리자 홈·센터 콘텐츠를 흉내 내는 모의 서버. 연락처는 하나만 두고 링크·게시 기간 규칙은 서버가 정하는 대로 따른다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, denyCsrf, denyUnless } from './auth';

type Content = Schemas['AdminContent'];
type ContentWrite = Schemas['AdminContentWrite'];
type ContentType = Schemas['ContentType'];

const cid = (n: number) => `20${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;

interface State {
  rows: Content[];
  seq: number;
  idempotent: Map<string, { fingerprint: string; body: Content }>;
}

function initialState(): State {
  const row = (n: number, contentType: ContentType, title: string, extra: Partial<Content> = {}): Content => ({
    contentId: cid(n), contentType, title, posted: true, periodStart: null, periodEnd: null, sortSeq: n, updatedOn: '2026-10-30', body: `${title} 본문입니다.`, url: null, contact: null, version: 1, ...extra,
  });
  const rows: Content[] = [
    row(1, 'VISUAL', '4분기 수강 안내 비주얼', { url: '/courses', sortSeq: 1 }),
    row(2, 'VISUAL', '센터 소개 비주얼', { url: '/center/history', sortSeq: 2 }),
    row(3, 'BANNER', '수강신청 접수 안내 배너', { url: '/guide/apply' }),
    row(4, 'BANNER', '접수 예정 안내 배너', { posted: false, url: '/courses/upcoming' }),
    row(5, 'POPUP', '휴관일 안내 팝업', { periodStart: '2026-11-01T00:00:00+09:00', periodEnd: '2026-11-10T23:59:00+09:00' }),
    row(6, 'HISTORY', '센터 연혁', { body: '2024.03 센터 개소\n2025.09 시설 확장\n2026.10 4분기 수강 접수' }),
    row(7, 'INTRO', '센터 소개'),
    row(8, 'CONTACT', '센터 연락처', { body: '', contact: { phone: '031-941-7742', adminOfficePhone: '031-940-8121', postalCode: '10937', address: '경기도 파주시 조리읍 봉천로 64', floorInfo: '조리읍 행정복지센터 3층', openHours: null, parking: null } }),
    row(9, 'GUIDE', '수강 및 결제 안내', { url: '/guide/apply' }),
    row(10, 'GUIDE', '환불 및 휴강 안내', { url: '/guide/refund' }),
    row(11, 'FACILITY', '시설안내'),
  ];
  return { rows, seq: 20, idempotent: new Map() };
}

let state = initialState();

/** 시험 사이에 콘텐츠를 처음 상태로 되돌린다. */
/** 첨부 모의 서버가 소유 콘텐츠를 확인할 때 쓰는 제목과 유형. 없으면 null이다. */
export const mockContentInfo = (contentId: string): { title: string; contentType: ContentType } | null => {
  const found = state.rows.find((row) => row.contentId === contentId);
  return found ? { title: found.title, contentType: found.contentType } : null;
};

export function resetMockContents(): void {
  state = initialState();
}

const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
const summary = (c: Content): Schemas['AdminContentSummary'] => ({ contentId: c.contentId, contentType: c.contentType, title: c.title, posted: c.posted, periodStart: c.periodStart, periodEnd: c.periodEnd, sortSeq: c.sortSeq, updatedOn: c.updatedOn });
const validUrl = (url: string) => url.startsWith('/') || url.startsWith('https://');

function validate(body: ContentWrite, ownId?: string): Record<string, string> | null {
  const fields: Record<string, string> = {};
  if (body.url && !validUrl(body.url.trim())) fields.url = '사이트 안 경로(/로 시작)나 https 주소만 쓸 수 있습니다.';
  if (body.periodStart && body.periodEnd && body.periodEnd <= body.periodStart) fields.periodEnd = '게시 종료는 시작 이후여야 합니다.';
  if (body.contentType === 'CONTACT' && !body.contact) fields.contact = '연락처 항목을 입력해 주세요.';
  if (body.contentType === 'CONTACT' && state.rows.some((row) => row.contentType === 'CONTACT' && row.contentId !== ownId)) fields.contentType = '연락처는 하나만 둘 수 있습니다.';
  if (body.contentType !== 'CONTACT' && !body.body.trim()) fields.body = '본문을 입력해 주세요.';
  return Object.keys(fields).length > 0 ? fields : null;
}

const normalize = (body: ContentWrite) => ({
  contentType: body.contentType,
  title: body.title.trim(),
  body: body.contentType === 'CONTACT' ? '' : body.body,
  url: body.url?.trim() || null,
  periodStart: body.periodStart ?? null,
  periodEnd: body.periodEnd ?? null,
  posted: body.posted,
  sortSeq: body.sortSeq,
  contact: body.contentType === 'CONTACT' ? (body.contact ?? null) : null,
});

export const contentHandlers = [
  http.get('/api/admin/v1/contents', ({ request }) => {
    const denied = denyUnless('AU.SITE_W');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const type = params.get('type');
    const rows = state.rows.filter((row) => !type || row.contentType === type).sort((a, b) => a.sortSeq - b.sortSeq || a.contentId.localeCompare(b.contentId));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    const canCreate = !(type === 'CONTACT' && rows.length > 0);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size).map(summary), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null }, canCreate });
  }),

  http.post('/api/admin/v1/contents', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.SITE_W');
    if (denied) return denied;
    const body = (await request.json()) as ContentWrite;
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(found.body, { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
    const fields = validate(body);
    if (fields) return apiError('RULE_REJECTED', fields);
    state.seq += 1;
    const created: Content = { ...normalize(body), contentId: cid(state.seq), updatedOn: today(), version: 1 };
    state.rows.push(created);
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: created });
    return HttpResponse.json(created, { status: 201 });
  }),

  http.get('/api/admin/v1/contents/:contentId', ({ params }) => {
    const denied = denyUnless('AU.SITE_W');
    if (denied) return denied;
    const row = state.rows.find((item) => item.contentId === params.contentId);
    return row ? HttpResponse.json(row) : apiError('NOT_FOUND');
  }),

  http.put('/api/admin/v1/contents/:contentId', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.SITE_W');
    if (denied) return denied;
    const row = state.rows.find((item) => item.contentId === params.contentId);
    if (!row) return apiError('NOT_FOUND');
    const { version, ...body } = (await request.json()) as Schemas['AdminContentUpdate'];
    if (version !== row.version) return apiError('VERSION_CONFLICT');
    if (body.contentType !== row.contentType) return apiError('RULE_REJECTED', { contentType: '콘텐츠 유형은 바꿀 수 없습니다.' });
    const fields = validate(body, row.contentId);
    if (fields) return apiError('RULE_REJECTED', fields);
    Object.assign(row, normalize(body), { updatedOn: today(), version: row.version + 1 });
    return HttpResponse.json(row);
  }),
];