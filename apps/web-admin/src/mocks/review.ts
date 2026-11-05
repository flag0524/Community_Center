// 관리자 강사 심사를 흉내 내는 모의 서버. 반려·활동중지 사유, 공개 조건, 되돌릴 수 없는 심사 결과는 서버가 정하는 대로 따른다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAuthorities, denyCsrf, denyUnless } from './auth';

type Review = Omit<Schemas['InstructorReview'], 'canReview'>;

const serial = (n: number) => `10${String(n).padStart(20, '0')}`;

interface State {
  reviews: Review[];
  seq: number;
  idempotent: Map<string, { fingerprint: string; body: Schemas['InstructorReview'] }>;
}

// 이름은 모두 지어낸 값이다. 실제 지원자 개인정보를 쓰지 않는다.
function initialState(): State {
  const row = (n: number, applicantName: string, desiredCourse: string, source: Review['source'], receivedOn: string, status: Review['status'], extra: Partial<Review> = {}): Review => ({
    applicationId: serial(n), applicantName, desiredCourse, categoryName: '문화/취미', career: `${desiredCourse} 지도 경력 ${n + 3}년`, source, receivedOn, status, isPublic: false, reason: null, memo: null, version: 1, ...extra,
  });
  return {
    reviews: [
      row(1, '김지원', '통기타 중급반', 'ONLINE', '2026-09-20', 'PENDING'),
      row(2, '박강사', '요가 입문반', 'ONLINE', '2026-09-12', 'APPROVED', { isPublic: true, memo: '증빙 확인 완료' }),
      row(3, '이신청', '한글 문해 교실', 'VISIT', '2026-09-25', 'REJECTED', { reason: '자격 증빙 미제출' }),
      row(4, '최보류', '라인댄스 B', 'EXTERNAL', '2026-10-02', 'PENDING'),
      row(5, '정중지', '생활영어 심화', 'ONLINE', '2026-08-30', 'SUSPENDED', { reason: '활동 중지 요청' }),
    ],
    seq: 5,
    idempotent: new Map(),
  };
}

let state = initialState();

/** 시험 사이에 심사 목록을 처음 상태로 되돌린다. */
export function resetMockReview(): void {
  state = initialState();
}

const withFlag = (review: Review): Schemas['InstructorReview'] => ({ ...review, canReview: currentAuthorities().includes('AU.INSTR_W') });
const PAGE_SIZE = 20;
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());

export const reviewHandlers = [
  http.get('/api/admin/v1/instructor-applications', ({ request }) => {
    const denied = denyUnless('AU.INSTR_W');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const q = params.get('q')?.trim();
    const isPublic = params.get('isPublic');
    const rows = state.reviews.filter(
      (review) =>
        (!q || review.applicantName.includes(q) || review.desiredCourse.includes(q)) &&
        (!params.get('status') || review.status === params.get('status')) &&
        (isPublic === null || review.isPublic === (isPublic === 'true')),
    );
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({
      items: rows.slice((page - 1) * size, page * size).map(({ applicationId, applicantName, desiredCourse, receivedOn, status, isPublic: open }) => ({ applicationId, applicantName, desiredCourse, receivedOn, status, isPublic: open })),
      page,
      size,
      total: rows.length,
      criteria: { basisAt: new Date().toISOString(), description: null },
    });
  }),

  http.post('/api/admin/v1/instructor-applications', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.INSTR_W');
    if (denied) return denied;
    const body = (await request.json()) as Schemas['InstructorReviewCreate'];
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(found.body, { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
    if (body.source === 'ONLINE') return apiError('RULE_REJECTED', { source: '온라인 지원은 접수할 수 없습니다. 방문 또는 외부 접수만 등록합니다.' });
    state.seq += 1;
    const created: Review = {
      applicationId: serial(state.seq), applicantName: body.applicantName, desiredCourse: body.desiredCourse, categoryName: null, career: body.career,
      source: body.source, receivedOn: today(), status: 'PENDING', isPublic: false, reason: null, memo: null, version: 1,
    };
    state.reviews.push(created);
    const result = withFlag(created);
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: result });
    return HttpResponse.json(result, { status: 201 });
  }),

  http.get('/api/admin/v1/instructor-applications/:applicationId', ({ params }) => {
    const denied = denyUnless('AU.INSTR_W');
    if (denied) return denied;
    const found = state.reviews.find((review) => review.applicationId === params.applicationId);
    return found ? HttpResponse.json(withFlag(found)) : apiError('NOT_FOUND');
  }),

  http.put('/api/admin/v1/instructor-applications/:applicationId', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.INSTR_W');
    if (denied) return denied;
    const found = state.reviews.find((review) => review.applicationId === params.applicationId);
    if (!found) return apiError('NOT_FOUND');
    const body = (await request.json()) as Schemas['InstructorReviewWrite'];
    if (body.version !== found.version) return apiError('VERSION_CONFLICT');
    const fields: Record<string, string> = {};
    if (body.status === 'PENDING' && found.status !== 'PENDING') fields.status = '심사 결과는 심사대기로 되돌릴 수 없습니다.';
    if ((body.status === 'REJECTED' || body.status === 'SUSPENDED') && !body.reason?.trim()) fields.reason = '반려·활동중지 사유를 입력해 주세요.';
    if (body.isPublic && body.status !== 'APPROVED') fields.isPublic = '승인된 강사만 공개할 수 있습니다.';
    if (Object.keys(fields).length > 0) return apiError('RULE_REJECTED', fields);
    const approvedOrOpen = body.status === 'APPROVED' || body.status === 'PENDING';
    Object.assign(found, {
      status: body.status,
      reason: approvedOrOpen ? null : body.reason!.trim(),
      isPublic: body.isPublic,
      memo: body.memo?.trim() || null,
      version: found.version + 1,
    });
    return HttpResponse.json(withFlag(found));
  }),
];