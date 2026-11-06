// 관리자 문의·답변을 흉내 내는 모의 서버. 답변은 원글당 한 단계이고 고치면 이력이 남으며 읽은 버전이 다르면 409다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, currentAuthorities, denyCsrf, denyUnless } from './auth';

type Inquiry = Schemas['AdminInquiry'];

const iid = (n: number) => `18${String(n).padStart(20, '0')}`;
const cid = (n: number) => `19${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;

// 문의 분류는 시안의 선택지이며 확정값이 아니다(PRD Q26).
const CATEGORIES = ['수강 신청', '결제·환불', '시설·장소', '기타'].map((name, index) => ({ id: cid(index + 1), name }));

interface Seed {
  n: number;
  title: string;
  category: number;
  author: string;
  isPrivate: boolean;
  received: string;
  content: string;
  answer?: { content: string; link: string | null; by: string; at: string };
}

const SEEDS: Seed[] = [
  { n: 1, title: '결제 확인 방법 문의', category: 2, author: '김○○', isPrivate: false, received: '2026-10-22', content: '카드 결제가 되었는지 어디서 확인하나요?' },
  { n: 2, title: '교육 장소 문의', category: 3, author: '이○○', isPrivate: true, received: '2026-10-20', content: '강의실 위치를 알려 주세요.', answer: { content: '3층 강의실 1입니다.', link: '/center/contact', by: '박정산', at: '2026-10-21T10:00:00+09:00' } },
  { n: 3, title: '수강신청 취소는 어떻게 하나요?', category: 1, author: '박○○', isPrivate: false, received: '2026-10-28', content: '신청을 취소하고 싶습니다.' },
  { n: 4, title: '준비물 문의', category: 1, author: '최○○', isPrivate: true, received: '2026-10-29', content: '준비물이 따로 있나요?' },
  { n: 5, title: '영수증 발급', category: 2, author: '정○○', isPrivate: false, received: '2026-10-15', content: '영수증은 어디서 받나요?', answer: { content: '내 신청 내역에서 받을 수 있습니다.', link: null, by: '김관리', at: '2026-10-16T09:00:00+09:00' } },
  { n: 6, title: '기타 문의', category: 4, author: '황○○', isPrivate: false, received: '2026-10-30', content: '센터 운영 시간이 궁금합니다.' },
];

function initialState(): Inquiry[] {
  return SEEDS.map((seed): Inquiry => ({
    inquiryId: iid(seed.n),
    title: seed.title,
    categoryName: CATEGORIES[seed.category - 1]!.name,
    authorName: seed.author,
    isPrivate: seed.isPrivate,
    status: seed.answer ? 'ANSWERED' : 'RECEIVED',
    receivedOn: seed.received,
    content: seed.content,
    answer: seed.answer ? { content: seed.answer.content, relatedLink: seed.answer.link, answeredBy: seed.answer.by, answeredAt: seed.answer.at, version: 1 } : null,
    history: seed.answer ? [{ at: seed.answer.at, by: seed.answer.by, action: 'CREATED' }] : [],
    canAnswer: false,
  }));
}

let state = initialState();

/** 시험 사이에 문의와 답변을 처음 상태로 되돌린다. */
export function resetMockInquiries(): void {
  state = initialState();
}

const view = (inquiry: Inquiry): Inquiry => ({ ...inquiry, canAnswer: currentAuthorities().includes('AU.POST_W') });
const summary = (i: Inquiry): Schemas['AdminInquirySummary'] => ({ inquiryId: i.inquiryId, title: i.title, categoryName: i.categoryName, authorName: i.authorName, isPrivate: i.isPrivate, status: i.status, receivedOn: i.receivedOn });
const validLink = (link: string) => link.startsWith('/') || link.startsWith('https://');

export const inquiryHandlers = [
  http.get('/api/admin/v1/inquiry-categories', () => {
    const denied = denyUnless('AU.POST_W');
    if (denied) return denied;
    return HttpResponse.json({ items: CATEGORIES } satisfies Schemas['AdminInquiryCategoryList']);
  }),

  http.get('/api/admin/v1/inquiries', ({ request }) => {
    const denied = denyUnless('AU.POST_W');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const q = params.get('q')?.trim();
    const categoryName = CATEGORIES.find((category) => category.id === params.get('categoryId'))?.name;
    const rows = state
      .filter((row) => (!params.get('status') || row.status === params.get('status')) && (!params.get('categoryId') || row.categoryName === categoryName) && (!q || row.title.includes(q)))
      // 답변을 기다리는 문의를 먼저, 오래된 것부터 보이고 나머지는 최근 접수가 앞이다.
      .sort((a, b) => Number(b.status === 'RECEIVED') - Number(a.status === 'RECEIVED') || (a.status === 'RECEIVED' ? a.receivedOn.localeCompare(b.receivedOn) : b.receivedOn.localeCompare(a.receivedOn)));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size).map(summary), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.get('/api/admin/v1/inquiries/:inquiryId', ({ params }) => {
    const denied = denyUnless('AU.POST_W');
    if (denied) return denied;
    const row = state.find((item) => item.inquiryId === params.inquiryId);
    return row ? HttpResponse.json(view(row)) : apiError('NOT_FOUND');
  }),

  http.put('/api/admin/v1/inquiries/:inquiryId/answer', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.POST_W');
    if (denied) return denied;
    const row = state.find((item) => item.inquiryId === params.inquiryId);
    if (!row) return apiError('NOT_FOUND');
    const body = (await request.json()) as Schemas['InquiryAnswerWrite'];
    if (body.version !== (row.answer?.version ?? 0)) return apiError('VERSION_CONFLICT');
    const link = body.relatedLink?.trim() || null;
    if (link && !validLink(link)) return apiError('RULE_REJECTED', { relatedLink: '사이트 안 경로(/로 시작)나 https 주소만 쓸 수 있습니다.' });
    if (!body.content.trim()) return apiError('RULE_REJECTED', { content: '답변 내용을 입력해 주세요.' });
    const now = new Date().toISOString();
    const by = currentAdminName();
    const created = row.answer === null;
    row.answer = { content: body.content.trim(), relatedLink: link, answeredBy: by, answeredAt: now, version: (row.answer?.version ?? 0) + 1 };
    row.status = 'ANSWERED';
    row.history.push({ at: now, by, action: created ? 'CREATED' : 'EDITED' });
    return HttpResponse.json(view(row));
  }),
];