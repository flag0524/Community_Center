// 수강신청 미리보기·신청·조회를 흉내 내는 모의 서버. 금액·정원·대기순번·결제기한은 서버가 정하고 화면은 따르기만 한다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, csrfRejected, currentMockMember, registerWithdrawalGuard } from './auth';
import { mockNow } from './clock';
import { buildCourseSummary, findCourseSeed } from './fixtures';
import { mockPayOutcome } from './payOutcome';

type Application = Schemas['Application'];
type ApplyPreview = Schemas['ApplyPreview'];

const PAYMENT_WINDOW_SECONDS = 600;

interface StoredApplication {
  memberId: string;
  courseId: string;
  idempotencyKey: string;
  application: Application;
}

interface StoredPayment {
  paymentId: string;
  orderNo: string;
  memberId: string;
  applicationId: string;
  amount: number;
  method: Schemas['PaymentMethod'];
  idempotencyKey: string;
}

interface MockApplicationState {
  items: Map<string, StoredApplication>;
  seq: number;
  payments: Map<string, StoredPayment>; // 주문번호로 찾는다
  paymentSeq: number;
  refunds: Map<string, { memberId: string; refund: Schemas['Refund'] }>;
  refundSeq: number;
}

const initialState = (): MockApplicationState => ({ items: new Map(), seq: 0, payments: new Map(), paymentSeq: 0, refunds: new Map(), refundSeq: 0 });
let state = initialState();

/** 수강확정(결제 완료·무료 등록)인 신청의 강좌. 후기를 쓸 수 있는 강좌의 기준이다. */
export function confirmedCoursesFor(memberId: string): Array<{ courseId: string; name: string }> {
  return forMember(memberId)
    .filter(({ application }) => application.status === 'CONFIRMED')
    .map(({ application }) => ({ courseId: application.course.courseId, name: application.course.name }));
}

/** 시험 사이에 신청 내역을 비운다. */
export function resetMockApplications(): void {
  state = initialState();
}

// 취소·만료되지 않은 신청이나 처리 중인 환불이 있으면 탈퇴할 수 없다.
registerWithdrawalGuard((memberId) => {
  const active = forMember(memberId).some(({ application }) => !['CANCELLED', 'EXPIRED'].includes(application.status));
  const refunding = [...state.refunds.values()].some((item) => item.memberId === memberId && item.refund.stage !== 'DONE' && item.refund.stage !== 'REJECTED');
  return active || refunding ? '진행 중인 수강신청·결제·환불이 있어 탈퇴할 수 없습니다. 신청 내역을 먼저 확인해 주세요.' : null;
});

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

const paymentSerialOf = (seq: number) => String(3_000_000_000_000_000_000_000n + BigInt(seq));

/** 결제기한이 지난 결제 대기·결제 실패 신청을 만료로 바꾼다. 서버가 시각으로 판정하는 부분이다. */
function syncExpiry(stored: StoredApplication, now: Date): Application {
  const current = stored.application;
  const open = current.displayState === 'PAYMENT_DUE' || current.displayState === 'PAYMENT_FAILED';
  if (open && current.paymentDeadline && now.getTime() > new Date(current.paymentDeadline).getTime()) {
    stored.application = { ...current, status: 'EXPIRED', displayState: 'EXPIRED', canPay: false, canCancel: false };
  }
  return stored.application;
}

function expire(stored: StoredApplication): void {
  stored.application = { ...stored.application, status: 'EXPIRED', displayState: 'EXPIRED', canPay: false, canCancel: false };
}
const reservedFor = (applicationId: string) =>
  [...state.refunds.values()]
    .filter((item) => item.refund.applicationId === applicationId && item.refund.stage !== 'REJECTED')
    .reduce((sum, item) => sum + item.refund.amount, 0);

/** 신청의 가장 최근 환불 단계를 응답에 붙인다. */
function withRefundStage(application: Application, memberId: string): Application {
  const latest = [...state.refunds.values()]
    .filter((item) => item.memberId === memberId && item.refund.applicationId === application.applicationId)
    .at(-1);
  return { ...application, refundStage: latest ? latest.refund.stage : null };
}

const kstYearMonth = (date: Date): [number, number] => {
  const [year, month] = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(date).split('-');
  return [Number(year), Number(month)];
};

/** 반환 기준액 산정을 흉내 낸다. 개강 전이면 전액, 개강 후에는 지난 달수와 당월분을 뺀 나머지다(PRD Q15, 기관 승인 전 값). */
function buildRefundPreview(application: Application, reserved: number, now: Date): Schemas['RefundPreview'] {
  const paid = application.payableAmount;
  const [startYear, startMonth] = application.course.educationStart.split('-').map(Number) as [number, number];
  const [endYear, endMonth] = application.course.educationEnd.split('-').map(Number) as [number, number];
  const educationMonths = (endYear - startYear) * 12 + (endMonth - startMonth) + 1;
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(now);
  const base = { applicationId: application.applicationId, paidAmount: paid, reservedAmount: reserved, serverNow: now.toISOString() };
  if (today < application.course.educationStart) {
    return { ...base, refundableAmount: paid, basis: { rule: 'BEFORE_START', referenceDate: today } };
  }
  const [year, month] = kstYearMonth(now);
  const elapsed = Math.min(educationMonths, (year - startYear) * 12 + (month - startMonth) + 1);
  const monthlyFee = Math.floor(paid / educationMonths);
  return {
    ...base,
    refundableAmount: monthlyFee * Math.max(0, educationMonths - elapsed),
    basis: { rule: 'AFTER_START', referenceDate: today, educationMonths, elapsedMonths: elapsed, monthlyFee },
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
    paymentId: null,
    refundStage: null,
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
      ? HttpResponse.json({ ...withRefundStage(syncExpiry(found, mockNow()), member.memberId), serverNow: mockNow().toISOString() })
      : apiError('NOT_FOUND');
  }),

  http.post('/api/v1/me/applications/:applicationId/payments', async ({ request, params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const key = request.headers.get('Idempotency-Key');
    if (!key) return apiError('VALIDATION_FAILED', { 'Idempotency-Key': '멱등키가 필요합니다.' });
    const found = state.items.get(String(params.applicationId));
    if (!found || found.memberId !== member.memberId) return apiError('NOT_FOUND');
    const { method } = (await request.json()) as Schemas['PaymentRequestCreate'];

    const now = mockNow();
    const application = syncExpiry(found, now);
    // 같은 키로 다시 요청하면 새로 만들지 않고 이전 결제 요청을 돌려준다. 기한은 늘어나지 않는다.
    const previous = [...state.payments.values()].find((item) => item.idempotencyKey === key);
    if (!previous) {
      if (application.displayState === 'PAYMENT_UNKNOWN') return apiError('PAY_RESULT_PENDING');
      if (application.displayState === 'EXPIRED') return apiError('PAY_DEADLINE_EXPIRED');
      if (!application.canPay) return apiError('PAY_NOT_PAYABLE');
    }
    const payment =
      previous ??
      (() => {
        state.paymentSeq += 1;
        const created: StoredPayment = {
          paymentId: paymentSerialOf(state.paymentSeq),
          orderNo: `MOCK-${String(state.paymentSeq).padStart(6, '0')}`,
          memberId: member.memberId,
          applicationId: application.applicationId,
          amount: application.payableAmount,
          method,
          idempotencyKey: key,
        };
        state.payments.set(created.orderNo, created);
        return created;
      })();
    return HttpResponse.json(
      {
        serverNow: now.toISOString(),
        paymentId: payment.paymentId,
        orderNo: payment.orderNo,
        amount: payment.amount,
        method,
        deadline: application.paymentDeadline!,
        gateway: 'mock',
        gatewayParams: {},
      },
      { status: 201 },
    );
  }),

  http.post('/api/v1/payments/confirm', async ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const body = (await request.json()) as Schemas['PaymentConfirmRequest'];
    const payment = state.payments.get(body.orderNo);
    const found = payment ? state.items.get(payment.applicationId) : undefined;
    if (!payment || !found || found.memberId !== member.memberId) return apiError('NOT_FOUND');
    // 금액은 저장한 값과 대조만 한다. 브라우저가 보낸 값으로 정하지 않는다.
    if (body.amount !== payment.amount) return apiError('PAY_AMOUNT_MISMATCH');

    const now = mockNow();
    const outcome = mockPayOutcome();
    const application = syncExpiry(found, now);
    if (application.displayState === 'PAYMENT_UNKNOWN') return apiError('PAY_RESULT_PENDING');
    if (outcome === 'expired' || application.displayState === 'EXPIRED') {
      expire(found);
      return apiError('PAY_DEADLINE_EXPIRED');
    }

    const settled =
      outcome === 'success'
        ? { status: 'CONFIRMED', displayState: 'CONFIRMED', paymentStatus: 'PAID', canPay: false, canCancel: false, canRequestRefund: true }
        : outcome === 'failed'
          ? { status: 'HOLD', displayState: 'PAYMENT_FAILED', paymentStatus: 'FAILED', canPay: true, canCancel: true, canRequestRefund: false }
          : { status: 'HOLD', displayState: 'PAYMENT_UNKNOWN', paymentStatus: 'PENDING', canPay: false, canCancel: false, canRequestRefund: false };
    found.application = { ...application, ...settled, paymentId: payment.paymentId } as Application;
    return HttpResponse.json({
      serverNow: now.toISOString(),
      paymentId: payment.paymentId,
      status: settled.paymentStatus,
      applicationId: application.applicationId,
      applicationDisplayState: settled.displayState,
    });
  }),

  http.get('/api/v1/me/applications', ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const params = new URL(request.url).searchParams;
    const page = Math.max(1, Number(params.get('page')) || 1);
    const size = Math.min(50, Math.max(1, Number(params.get('size')) || 10));
    const now = mockNow();
    const mine = forMember(member.memberId)
      .map((item) => withRefundStage(syncExpiry(item, now), member.memberId))
      .reverse(); // 최신 신청이 먼저
    // 목록 항목은 ApplicationSummary라 응답 시각(serverNow)은 싣지 않는다.
    const items = mine.slice((page - 1) * size, page * size).map((item) => {
      const { serverNow, ...summary } = item;
      void serverNow;
      return summary;
    });
    return HttpResponse.json({
      items,
      page,
      size,
      total: mine.length,
      criteria: { basisAt: now.toISOString(), description: null },
    });
  }),

  http.post('/api/v1/me/applications/:applicationId/cancel', ({ request, params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const found = state.items.get(String(params.applicationId));
    if (!found || found.memberId !== member.memberId) return apiError('NOT_FOUND');
    const application = syncExpiry(found, mockNow());
    if (application.displayState === 'PAYMENT_UNKNOWN') return apiError('PAY_RESULT_PENDING');
    if (!application.canCancel) return apiError('APLY_CANCEL_NOT_ALLOWED');
    found.application = {
      ...application,
      status: 'CANCELLED',
      displayState: 'CANCELLED',
      canPay: false,
      canCancel: false,
      canRequestRefund: false,
      serverNow: mockNow().toISOString(),
    };
    return HttpResponse.json(found.application);
  }),

  http.get('/api/v1/me/payments/:paymentId/receipt', ({ params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const payment = [...state.payments.values()].find((item) => item.paymentId === String(params.paymentId));
    const found = payment ? state.items.get(payment.applicationId) : undefined;
    if (!payment || !found || found.memberId !== member.memberId || found.application.paymentStatus !== 'PAID') {
      return apiError('NOT_FOUND');
    }
    return HttpResponse.json({
      paymentId: payment.paymentId,
      applicationId: payment.applicationId,
      courseName: found.application.course.name,
      method: payment.method,
      amount: payment.amount,
      approvalNo: `MOCK-${payment.orderNo.slice(-6)}`,
      approvedAt: mockNow().toISOString(),
      payerName: member.name,
    });
  }),

  http.get('/api/v1/me/applications/:applicationId/refund-preview', ({ params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const found = state.items.get(String(params.applicationId));
    if (!found || found.memberId !== member.memberId) return apiError('NOT_FOUND');
    const now = mockNow();
    const application = syncExpiry(found, now);
    const reserved = reservedFor(application.applicationId);
    if (reserved === 0 && !application.canRequestRefund) return apiError('RFND_NOT_ALLOWED');
    return HttpResponse.json(buildRefundPreview(application, reserved, now));
  }),

  http.post('/api/v1/me/refunds', async ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const key = request.headers.get('Idempotency-Key');
    if (!key) return apiError('VALIDATION_FAILED', { 'Idempotency-Key': '멱등키가 필요합니다.' });
    const body = (await request.json()) as Schemas['RefundCreate'];
    const found = state.items.get(body.applicationId);
    if (!found || found.memberId !== member.memberId) return apiError('NOT_FOUND');
    const now = mockNow();
    const application = syncExpiry(found, now);
    const reserved = reservedFor(application.applicationId);
    if (reserved === 0 && !application.canRequestRefund) return apiError('RFND_NOT_ALLOWED');
    const preview = buildRefundPreview(application, reserved, now);
    const amount = preview.refundableAmount - reserved; // 금액은 서버가 정한다. 요청에는 없다.
    if (amount <= 0) return apiError('RFND_LIMIT_EXCEEDED');

    state.refundSeq += 1;
    const refund: Schemas['Refund'] = {
      refundId: String(4_000_000_000_000_000_000_000n + BigInt(state.refundSeq)),
      applicationId: application.applicationId,
      courseName: application.course.name,
      amount,
      status: 'REQUESTED',
      stage: 'RECEIVED',
      reason: null,
      requestedAt: now.toISOString(),
      completedAt: null,
    };
    state.refunds.set(refund.refundId, { memberId: member.memberId, refund });
    found.application = { ...application, canRequestRefund: false };
    return HttpResponse.json(refund, { status: 201 });
  }),

  http.get('/api/v1/me/refunds', ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const params = new URL(request.url).searchParams;
    const page = Math.max(1, Number(params.get('page')) || 1);
    const size = Math.min(50, Math.max(1, Number(params.get('size')) || 10));
    const mine = [...state.refunds.values()].filter((item) => item.memberId === member.memberId).map((item) => item.refund).reverse();
    return HttpResponse.json({
      items: mine.slice((page - 1) * size, page * size),
      page,
      size,
      total: mine.length,
      criteria: { basisAt: mockNow().toISOString(), description: null },
    });
  }),];
