// 질문과 답변(문의)과 수강후기를 흉내 내는 모의 서버. 다른 회원의 비공개 문의 가림, 본인 글만 수정·삭제, 수강확정 강좌의 후기만 작성을 서버가 정한다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { confirmedCoursesFor } from './applications';
import { apiError, csrfRejected, currentMockMember } from './auth';
import { registerOwnerInfo } from './files';

type Inquiry = Schemas['InquiryDetail'];
type Review = Schemas['ReviewDetail'];

const OTHER = { memberId: '1000000000000000000009', name: '김다른' };
const CATEGORIES = [
  { categoryId: 'IQ.COURSE', name: '수강신청' },
  { categoryId: 'IQ.PAYMENT', name: '결제' },
  { categoryId: 'IQ.REFUND', name: '환불' },
  { categoryId: 'IQ.CENTER', name: '센터 이용' },
];

interface StoredInquiry extends Omit<Inquiry, 'canEdit' | 'canDelete' | 'status'> {
  authorId: string;
}
interface StoredReview extends Omit<Review, 'canEdit' | 'canDelete'> {
  authorId: string;
  idempotencyKey?: string;
}

interface CommunityState {
  inquiries: Map<string, StoredInquiry>;
  reviews: Map<string, StoredReview>;
  seq: number;
  keys: Map<string, string>;
}

const DEMO_ID = '1000000000000000000001';

const seedInquiries = (): StoredInquiry[] => [
  {
    postId: '601',
    categoryId: 'IQ.PAYMENT',
    categoryName: '결제',
    title: '결제 결과는 어디서 확인하나요?',
    body: '수강료 결제를 진행했습니다. 신청 내역에서 결과를 확인하는 방법을 알고 싶습니다.',
    authorId: DEMO_ID,
    authorName: '예시회원',
    isPrivate: true,
    publishedAt: '2026-10-06T10:00:00+09:00',
    answer: {
      body: '마이페이지의 신청 상세에서 결제상태를 확인하실 수 있습니다. 승인 결과 확인 중에는 재결제하지 않고 결과 안내를 기다려 주세요.',
      answeredAt: '2026-10-07T10:00:00+09:00',
    },
  },
  {
    postId: '602',
    categoryId: 'IQ.COURSE',
    categoryName: '수강신청',
    title: '대기신청 순번 문의',
    body: '대기신청 순번이 어떻게 정해지나요?',
    authorId: DEMO_ID,
    authorName: '예시회원',
    isPrivate: true,
    publishedAt: '2026-10-05T10:00:00+09:00',
    answer: null,
  },
  {
    postId: '603',
    categoryId: 'IQ.REFUND',
    categoryName: '환불',
    title: '다른 회원의 문의',
    body: '다른 회원이 쓴 비공개 문의입니다.',
    authorId: OTHER.memberId,
    authorName: OTHER.name,
    isPrivate: true,
    publishedAt: '2026-10-04T10:00:00+09:00',
    answer: null,
  },
  {
    postId: '604',
    categoryId: 'IQ.CENTER',
    categoryName: '센터 이용',
    title: '수강 시간 문의',
    body: '수강 시간이 궁금합니다.',
    authorId: OTHER.memberId,
    authorName: OTHER.name,
    isPrivate: false,
    publishedAt: '2026-10-03T10:00:00+09:00',
    answer: null,
  },
];

const initialState = (): CommunityState => ({
  inquiries: new Map(seedInquiries().map((item) => [item.postId, item])),
  reviews: new Map(),
  seq: 700,
  keys: new Map(),
});

let state = initialState();

// 문의 첨부는 내 문의에 답변이 달리기 전에만 더하거나 지울 수 있다.
registerOwnerInfo('inquiries', (id, memberId) => {
  const item = state.inquiries.get(id);
  return item && item.authorId === memberId ? { locked: item.answer !== null && item.answer !== undefined } : null;
});

/** 시험 사이에 문의·후기를 처음으로 되돌린다. */
export function resetMockCommunity(): void {
  state = initialState();
}

const maskName = (name: string) => `${name.slice(0, 1)}${'*'.repeat(Math.max(1, name.length - 1))}`;
const status = (item: StoredInquiry) => (item.answer ? ('ANSWERED' as const) : ('RECEIVED' as const));
const byDateDesc = <T extends { publishedAt: string }>(a: T, b: T) => b.publishedAt.localeCompare(a.publishedAt);

function inquirySummary(item: StoredInquiry, memberId: string): Schemas['InquirySummary'] {
  const mine = item.authorId === memberId;
  const hidden = item.isPrivate && !mine;
  return {
    postId: item.postId,
    categoryName: item.categoryName,
    title: hidden ? '비공개 문의입니다.' : item.title,
    authorName: mine ? item.authorName : maskName(item.authorName),
    status: status(item),
    isPrivate: item.isPrivate,
    isMine: mine,
    publishedAt: item.publishedAt,
  };
}

function inquiryDetail(item: StoredInquiry, memberId: string): Inquiry {
  const mine = item.authorId === memberId;
  return {
    postId: item.postId,
    categoryId: item.categoryId,
    categoryName: item.categoryName,
    title: item.title,
    body: item.body,
    authorName: mine ? item.authorName : maskName(item.authorName),
    status: status(item),
    isPrivate: item.isPrivate,
    publishedAt: item.publishedAt,
    answer: item.answer,
    canEdit: mine && !item.answer,
    canDelete: mine,
  };
}

function reviewDetail(item: StoredReview, memberId: string): Review {
  const { authorId, idempotencyKey: _key, ...rest } = item;
  void _key;
  const mine = authorId === memberId;
  return { ...rest, canEdit: mine, canDelete: mine };
}

function reviewSummary(item: StoredReview, memberId: string): Schemas['ReviewSummary'] {
  return {
    postId: item.postId,
    title: item.title,
    authorName: item.authorId === memberId ? item.authorName : maskName(item.authorName),
    courseName: item.courseName,
    isMine: item.authorId === memberId,
    publishedAt: item.publishedAt,
  };
}

const paging = (url: string) => {
  const search = new URL(url).searchParams;
  return {
    q: search.get('q')?.trim().toLowerCase(),
    page: Math.max(1, Number(search.get('page')) || 1),
    size: Math.min(50, Math.max(1, Number(search.get('size')) || 10)),
  };
};

const pageOf = <T>(items: T[], page: number, size: number) => ({
  items: items.slice((page - 1) * size, page * size),
  page,
  size,
  total: items.length,
  criteria: { basisAt: new Date().toISOString(), description: null },
});

const empty = (fields: Record<string, string>) => Object.keys(fields).length > 0;
const validate = (body: { title?: string; body?: string }) => {
  const fields: Record<string, string> = {};
  if (!body.title?.trim()) fields.title = '제목을 입력해 주세요.';
  if (!body.body?.trim()) fields.body = '내용을 입력해 주세요.';
  return fields;
};
const now = () => new Date().toISOString();

export const communityHandlers = [
  http.get('/api/v1/inquiry-categories', () => {
    if (!currentMockMember()) return apiError('UNAUTHENTICATED');
    return HttpResponse.json({ items: CATEGORIES });
  }),

  http.get('/api/v1/inquiries', ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const { page, size } = paging(request.url);
    const all = [...state.inquiries.values()].sort(byDateDesc).map((item) => inquirySummary(item, member.memberId));
    return HttpResponse.json(pageOf(all, page, size));
  }),

  http.get('/api/v1/inquiries/:postId', ({ params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const item = state.inquiries.get(String(params.postId));
    // 다른 회원의 비공개 문의는 없는 것과 같게 404다.
    if (!item || (item.isPrivate && item.authorId !== member.memberId)) return apiError('NOT_FOUND');
    return HttpResponse.json(inquiryDetail(item, member.memberId));
  }),

  http.get('/api/v1/me/inquiries', ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const { page, size } = paging(request.url);
    const mine = [...state.inquiries.values()].filter((item) => item.authorId === member.memberId).sort(byDateDesc);
    return HttpResponse.json(pageOf(mine.map((item) => inquirySummary(item, member.memberId)), page, size));
  }),

  http.post('/api/v1/me/inquiries', async ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const key = request.headers.get('Idempotency-Key');
    if (!key) return apiError('VALIDATION_FAILED', { 'Idempotency-Key': '멱등키가 필요합니다.' });
    const known = state.keys.get(key);
    if (known) return HttpResponse.json(inquiryDetail(state.inquiries.get(known)!, member.memberId), { status: 201 });
    const body = (await request.json()) as Schemas['InquiryWrite'];
    const fields = validate(body);
    const category = CATEGORIES.find((item) => item.categoryId === body.categoryId);
    if (!category) fields.categoryId = '문의 분류를 확인해 주세요.';
    if (empty(fields)) return apiError('VALIDATION_FAILED', fields);
    state.seq += 1;
    const item: StoredInquiry = {
      postId: String(state.seq),
      categoryId: category!.categoryId,
      categoryName: category!.name,
      title: body.title.trim(),
      body: body.body.trim(),
      authorId: member.memberId,
      authorName: member.name,
      isPrivate: body.isPrivate,
      publishedAt: now(),
      answer: null,
    };
    state.inquiries.set(item.postId, item);
    state.keys.set(key, item.postId);
    return HttpResponse.json(inquiryDetail(item, member.memberId), { status: 201 });
  }),

  http.put('/api/v1/me/inquiries/:postId', async ({ request, params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const item = state.inquiries.get(String(params.postId));
    if (!item || item.authorId !== member.memberId) return apiError('NOT_FOUND');
    if (item.answer) {
      return HttpResponse.json(
        { code: 'RULE_REJECTED', message: '답변이 달린 문의는 고칠 수 없습니다.', fields: null, requestId: 'mock-rule_rejected-0001' },
        { status: 422 },
      );
    }
    const body = (await request.json()) as Schemas['InquiryWrite'];
    const fields = validate(body);
    const category = CATEGORIES.find((entry) => entry.categoryId === body.categoryId);
    if (!category) fields.categoryId = '문의 분류를 확인해 주세요.';
    if (empty(fields)) return apiError('VALIDATION_FAILED', fields);
    Object.assign(item, {
      categoryId: category!.categoryId,
      categoryName: category!.name,
      title: body.title.trim(),
      body: body.body.trim(),
      isPrivate: body.isPrivate,
    });
    return HttpResponse.json(inquiryDetail(item, member.memberId));
  }),

  http.delete('/api/v1/me/inquiries/:postId', ({ request, params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const item = state.inquiries.get(String(params.postId));
    if (!item || item.authorId !== member.memberId) return apiError('NOT_FOUND');
    state.inquiries.delete(item.postId);
    return new HttpResponse(null, { status: 204 });
  }),

  http.get('/api/v1/reviews', ({ request }) => {
    const { q, page, size } = paging(request.url);
    const memberId = currentMockMember()?.memberId ?? '';
    const all = [...state.reviews.values()]
      .filter((item) => !q || item.title.toLowerCase().includes(q))
      .sort(byDateDesc)
      .map((item) => reviewSummary(item, memberId));
    return HttpResponse.json(pageOf(all, page, size));
  }),

  http.get('/api/v1/reviews/:postId', ({ params }) => {
    const item = state.reviews.get(String(params.postId));
    return item ? HttpResponse.json(reviewDetail(item, currentMockMember()?.memberId ?? '')) : apiError('NOT_FOUND');
  }),

  http.get('/api/v1/me/reviews', ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const { page, size } = paging(request.url);
    const mine = [...state.reviews.values()].filter((item) => item.authorId === member.memberId).sort(byDateDesc);
    return HttpResponse.json(pageOf(mine.map((item) => reviewSummary(item, member.memberId)), page, size));
  }),

  http.get('/api/v1/me/reviewable-courses', () => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    return HttpResponse.json({ items: confirmedCoursesFor(member.memberId) });
  }),

  http.post('/api/v1/me/reviews', async ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const key = request.headers.get('Idempotency-Key');
    if (!key) return apiError('VALIDATION_FAILED', { 'Idempotency-Key': '멱등키가 필요합니다.' });
    const known = state.keys.get(key);
    if (known) return HttpResponse.json(reviewDetail(state.reviews.get(known)!, member.memberId), { status: 201 });
    const body = (await request.json()) as Schemas['ReviewWrite'];
    const fields = validate(body);
    if (empty(fields)) return apiError('VALIDATION_FAILED', fields);
    // 직접 요청도 같은 검사를 한다. 수강확정인 강좌의 후기만 쓸 수 있다.
    const course = confirmedCoursesFor(member.memberId).find((item) => item.courseId === body.courseId);
    if (!course) {
      return HttpResponse.json(
        { code: 'RULE_REJECTED', message: '수강확정인 강좌의 후기만 쓸 수 있습니다.', fields: null, requestId: 'mock-rule_rejected-0001' },
        { status: 422 },
      );
    }
    state.seq += 1;
    const item: StoredReview = {
      postId: String(state.seq),
      courseId: course.courseId,
      courseName: course.name,
      title: body.title.trim(),
      body: body.body.trim(),
      authorId: member.memberId,
      authorName: member.name,
      publishedAt: now(),
    };
    state.reviews.set(item.postId, item);
    state.keys.set(key, item.postId);
    return HttpResponse.json(reviewDetail(item, member.memberId), { status: 201 });
  }),

  http.put('/api/v1/me/reviews/:postId', async ({ request, params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const item = state.reviews.get(String(params.postId));
    if (!item || item.authorId !== member.memberId) return apiError('NOT_FOUND');
    const body = (await request.json()) as Schemas['ReviewWrite'];
    const fields = validate(body);
    if (empty(fields)) return apiError('VALIDATION_FAILED', fields);
    Object.assign(item, { title: body.title.trim(), body: body.body.trim() });
    return HttpResponse.json(reviewDetail(item, member.memberId));
  }),

  http.delete('/api/v1/me/reviews/:postId', ({ request, params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const item = state.reviews.get(String(params.postId));
    if (!item || item.authorId !== member.memberId) return apiError('NOT_FOUND');
    state.reviews.delete(item.postId);
    return new HttpResponse(null, { status: 204 });
  }),
];