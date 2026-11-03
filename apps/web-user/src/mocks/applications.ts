// 수강신청 미리보기·신청·조회를 흉내 내는 모의 서버. 금액·정원·대기순번·결제기한은 서버가 정하고 화면은 따르기만 한다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, csrfRejected, currentMockMember } from './auth';
import { mockNow } from './clock';
import { buildCourseSummary, findCourseSeed } from './fixtures';

type Application = Schemas['Application'];
type ApplyPreview = Schemas['ApplyPreview'];

const PAYMENT_WINDOW_SECONDS = 600;

interface StoredApplication {
  memberId: string;
  courseId: string;
  idempotencyKey: string;
  application: Application;
}

interface MockApplicationState {
  items: Map<string, StoredApplication>;
  seq: number;
}

const initialState = (): MockApplicationState => ({ items: new Map(), seq: 0 });
let state = initialState();

/** 시험 사이에 신청 내역을 비운다. */
export function resetMockApplications(): void {
  state = initialState();
}

const serialOf = (seq: number) => String(2_000_000_000_000_000_000_000n + BigInt(seq));

const forMember = (memberId: string) => [...state.items.values()].filter((item) => item.memberId === memberId);
const activeFor = (memberId: string, courseId: string) =>
  forMember(memberId).find((item) => item.courseId === courseId);

function buildPreview(courseId: string, memberId: string, now: Date): ApplyPreview | null {
  const seed = findCourseSeed(courseId);
  if (!seed) return null;
  const course = buildCourseSummary(seed, now);
  const alreadyApplied = activeFor(memberId, courseId) !== undefined;
  let eligibility: ApplyPreview['eligibility'] = { canApply: true };
  if (alreadyApplied) {
    eligibility = { canApply: false, reasonCode: 'APLY_ALREADY_APPLIED', reasonMessage: '이미 신청한 강좌입니다.' };
  } else if (course.receptionState !== 'OPEN') {
    eligibility = { canApply: false, reasonCode: 'APLY_RCPT_CLOSED', reasonMessage: '접수기간이 아닙니다.' };
  }
  return {
    serverNow: now.toISOString(),
    course,
    fee: seed.fee,
    reductionAmount: 0,
    payableAmount: seed.fee,
    paymentWindowSeconds: PAYMENT_WINDOW_SECONDS,
    eligibility,
    residentPriorityActive: false,
    alreadyApplied,
  };
}

function createApplication(courseId: string, memberId: string, now: Date): Application {
  const seed = findCourseSeed(courseId)!;
  const course = buildCourseSummary(seed, now);
  state.seq += 1;
  const base = {
    applicationId: serialOf(state.seq),
    course,
    paymentStatus: null,
    fee: seed.fee,
    reductionAmount: 0,
    payableAmount: seed.fee,
    appliedAt: now.toISOString(),
    canRequestRefund: false,
    serverNow: now.toISOString(),
  };
  if (course.remainingSeats === 0) {
    const ahead = [...state.items.values()].filter(
      (item) => item.courseId === courseId && item.application.status === 'WAITING',
    ).length;
    return {
      ...base,
      status: 'WAITING',
      displayState: 'WAITING',
      waitingRank: course.waitingCount + ahead + 1,
      seatAssignedAt: null,
      paymentDeadline: null,
      canCancel: true,
      canPay: false,
    };
  }
  if (seed.fee === 0) {
    return {
      ...base,
      status: 'CONFIRMED',
      displayState: 'CONFIRMED_FREE',
      waitingRank: null,
      seatAssignedAt: now.toISOString(),
      paymentDeadline: null,
      canCancel: true,
      canPay: false,
    };
  }
  return {
    ...base,
    status: 'HOLD',
    displayState: 'PAYMENT_DUE',
    waitingRank: null,
    seatAssignedAt: now.toISOString(),
    paymentDeadline: new Date(now.getTime() + PAYMENT_WINDOW_SECONDS * 1000).toISOString(),
    canCancel: true,
    canPay: true,
  };
}

export const applicationHandlers = [
  http.get('/api/v1/courses/:courseId/apply-preview', ({ params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const preview = buildPreview(String(params.courseId), member.memberId, mockNow());
    return preview ? HttpResponse.json(preview) : apiError('NOT_FOUND');
  }),

  http.post('/api/v1/me/applications', async ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const key = request.headers.get('Idempotency-Key');
    if (!key) return apiError('VALIDATION_FAILED', { 'Idempotency-Key': '멱등키가 필요합니다.' });
    const { courseId } = (await request.json()) as Schemas['ApplicationCreate'];

    // 같은 키와 같은 내용이면 이전 결과를 그대로, 같은 키에 다른 내용이면 409다.
    const previous = [...state.items.values()].find((item) => item.memberId === member.memberId && item.idempotencyKey === key);
    if (previous) {
      return previous.courseId === courseId
        ? HttpResponse.json(previous.application, { status: 201 })
        : apiError('IDEMPOTENCY_CONFLICT');
    }

    const now = mockNow();
    const preview = buildPreview(courseId, member.memberId, now);
    if (!preview) return apiError('NOT_FOUND');
    if (!preview.eligibility.canApply) return apiError(preview.eligibility.reasonCode!);

    const application = createApplication(courseId, member.memberId, now);
    state.items.set(application.applicationId, { memberId: member.memberId, courseId, idempotencyKey: key, application });
    return HttpResponse.json(application, { status: 201 });
  }),

  http.get('/api/v1/me/applications/:applicationId', ({ params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const found = state.items.get(String(params.applicationId));
    // 남의 신청은 없는 것과 같게 404로 답한다.
    return found && found.memberId === member.memberId
      ? HttpResponse.json({ ...found.application, serverNow: mockNow().toISOString() })
      : apiError('NOT_FOUND');
  }),
];
