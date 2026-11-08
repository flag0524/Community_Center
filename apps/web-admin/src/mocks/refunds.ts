// 관리자 환불 검토를 흉내 내는 모의 서버. 한도 검사, 접수·보류·승인·반려·집행·이체 확인 상태 전이, 승인자와 집행자 분리를 서버가 정하는 대로 따른다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { csvResponse } from './csv';
import { apiError, currentAdminId, currentAdminName, currentAuthorities, denyCsrf, denyUnless } from './auth';
import { countOwnerFiles, registerOwnerInfo } from './files';

type Refund = Schemas['AdminRefund'];
type Status = Schemas['RefundStatus'];
type Method = Schemas['ExecutionMethod'];

const rid = (n: number) => `14${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;
const FINANCE_ID = '2000000000000000000003'; // 시험 계정 박정산(결제·환불 담당자)
const RESERVED: Status[] = ['DONE', 'APPROVED', 'PENDING'];

interface Payment {
  orderNo: string;
  courseName: string;
  paid: number;
  method: Schemas['PaymentMethod'];
  paidAt: string;
  educationStart: string;
  /** 승인 시 산정하는 기준액. 모의 서버는 값을 고정해 둔다. */
  baseline: number;
  rule: Schemas['RefundRule'];
}

const PAYMENTS: Record<string, Payment> = {
  'A20264-000201': { orderNo: 'ORD-20260907-000001', courseName: '초급컴퓨터', paid: 60000, method: 'CARD', paidAt: '2026-09-07T09:03:00+09:00', educationStart: '2026-10-01', baseline: 40000, rule: 'AFTER_START' },
  'A20264-000202': { orderNo: 'ORD-20260907-000007', courseName: '생활영어', paid: 60000, method: 'CARD', paidAt: '2026-09-07T09:10:00+09:00', educationStart: '2026-10-01', baseline: 40000, rule: 'AFTER_START' },
  'A20264-000206': { orderNo: 'ORD-20260907-000006', courseName: '초급컴퓨터', paid: 60000, method: 'CARD', paidAt: '2026-09-07T09:08:00+09:00', educationStart: '2026-10-01', baseline: 40000, rule: 'AFTER_START' },
  'A20264-000207': { orderNo: 'ORD-20260907-000008', courseName: '통기타', paid: 30000, method: 'CARD', paidAt: '2026-09-07T09:20:00+09:00', educationStart: '2026-10-01', baseline: 20000, rule: 'AFTER_START' },
  'A20264-000208': { orderNo: 'ORD-20260907-000009', courseName: '라인댄스 A', paid: 30000, method: 'TRANSFER', paidAt: '2026-09-07T09:30:00+09:00', educationStart: '2026-10-01', baseline: 20000, rule: 'AFTER_START' },
  'A20264-000211': { orderNo: 'ORD-20260907-000005', courseName: '요가A(중급)', paid: 60000, method: 'TRANSFER', paidAt: '2026-09-09T09:32:00+09:00', educationStart: '2026-10-01', baseline: 40000, rule: 'AFTER_START' },
};

interface Row {
  refund: Omit<Refund, 'canReview' | 'canExecute' | 'canConfirmTransfer' | 'executeNote' | 'reservedAmount' | 'remainingAmount'>;
  approverId: string | null;
  /** 집행하면 PG가 돌려주는 결과. 수동 계좌환불은 이 값과 무관하게 이체 확인을 기다린다. */
  pgOutcome: 'DONE' | 'FAILED' | 'PENDING';
}

interface Seed {
  n: number;
  applicationNo: string;
  amount: number;
  status: Status;
  requester: Schemas['RefundRequester'];
  requesterName: string;
  received: string;
  elapsed: number;
  reason: string;
  method?: Method;
  approved?: number;
  approverId?: string;
  approverName?: string;
  decisionReason?: string;
  executedBy?: string;
  result?: string;
  pgOutcome?: Row['pgOutcome'];
  history: Array<[string, Status, string, string | null]>;
  evidence?: number;
}

const SEEDS: Seed[] = [
  { n: 11, applicationNo: 'A20264-000211', amount: 60000, status: 'REQUESTED', requester: 'MEMBER', requesterName: '오○○', received: '2026-09-09', elapsed: 2, reason: '개인 사정', evidence: 1, history: [['2026-09-09T13:10:00+09:00', 'REQUESTED', '회원', '본인 요청']] },
  { n: 12, applicationNo: 'A20264-000201', amount: 20000, status: 'ON_HOLD', requester: 'ADMIN', requesterName: '박정산', received: '2026-09-07', elapsed: 4, reason: '수강 불가', decisionReason: '증빙 확인 필요', history: [['2026-09-07T11:00:00+09:00', 'REQUESTED', '박정산', '방문·유선 접수'], ['2026-09-08T10:00:00+09:00', 'ON_HOLD', '박정산', '증빙 확인 필요']] },
  { n: 13, applicationNo: 'A20264-000202', amount: 40000, status: 'APPROVED', requester: 'MEMBER', requesterName: '이○○', received: '2026-09-08', elapsed: 1, reason: '일정 변경', approved: 40000, approverId: FINANCE_ID, approverName: '박정산', pgOutcome: 'DONE', history: [['2026-09-08T09:00:00+09:00', 'REQUESTED', '회원', '본인 요청'], ['2026-09-08T15:00:00+09:00', 'APPROVED', '박정산', '승인액 40,000원']] },
  { n: 14, applicationNo: 'A20264-000201', amount: 20000, status: 'PENDING', requester: 'MEMBER', requesterName: '김○○', received: '2026-09-06', elapsed: 3, reason: '개인 사정', approved: 20000, approverId: FINANCE_ID, approverName: '박정산', method: 'MANUAL_TRANSFER', executedBy: '김관리', result: '이체 대기 중입니다.', history: [['2026-09-06T09:00:00+09:00', 'REQUESTED', '회원', '본인 요청'], ['2026-09-06T14:00:00+09:00', 'APPROVED', '박정산', '승인액 20,000원'], ['2026-09-07T09:00:00+09:00', 'PENDING', '김관리', '집행 요청(수동 계좌환불)']] },
  { n: 15, applicationNo: 'A20264-000207', amount: 30000, status: 'FAILED', requester: 'MEMBER', requesterName: '박○○', received: '2026-09-05', elapsed: 4, reason: '건강 문제', approved: 30000, approverId: FINANCE_ID, approverName: '박정산', executedBy: '김관리', result: 'PG 취소 요청이 실패했습니다.', pgOutcome: 'DONE', history: [['2026-09-05T09:00:00+09:00', 'REQUESTED', '회원', '본인 요청'], ['2026-09-05T12:00:00+09:00', 'APPROVED', '박정산', '승인액 30,000원'], ['2026-09-06T09:00:00+09:00', 'FAILED', 'SYSTEM', 'PG 취소 요청 실패']] },
  { n: 17, applicationNo: 'A20264-000208', amount: 20000, status: 'APPROVED', requester: 'MEMBER', requesterName: '조○○', received: '2026-09-04', elapsed: 3, reason: '이사', method: 'MANUAL_TRANSFER', approved: 20000, approverId: FINANCE_ID, approverName: '박정산', history: [['2026-09-04T09:00:00+09:00', 'REQUESTED', '회원', '본인 요청'], ['2026-09-04T13:00:00+09:00', 'APPROVED', '박정산', '승인액 20,000원']] },
  { n: 6, applicationNo: 'A20264-000206', amount: 60000, status: 'DONE', requester: 'MEMBER', requesterName: '강○○', received: '2026-09-02', elapsed: 5, reason: '이사', approved: 60000, approverId: FINANCE_ID, approverName: '박정산', executedBy: '김관리', result: '원결제가 취소되었습니다.', history: [['2026-09-02T09:00:00+09:00', 'REQUESTED', '회원', '본인 요청'], ['2026-09-02T11:00:00+09:00', 'APPROVED', '박정산', '승인액 60,000원'], ['2026-09-03T09:00:00+09:00', 'DONE', 'SYSTEM', 'PG 취소 확인']] },
  { n: 16, applicationNo: 'A20264-000201', amount: 10000, status: 'REJECTED', requester: 'MEMBER', requesterName: '김○○', received: '2026-09-01', elapsed: 6, reason: '단순 변심', decisionReason: '환불 기준에 해당하지 않습니다.', history: [['2026-09-01T09:00:00+09:00', 'REQUESTED', '회원', '본인 요청'], ['2026-09-02T09:00:00+09:00', 'REJECTED', '박정산', '환불 기준에 해당하지 않습니다.']] },
];

function initialState(): Row[] {
  return SEEDS.map((seed): Row => {
    const payment = PAYMENTS[seed.applicationNo]!;
    const method: Method = seed.method ?? 'CANCEL_PAYMENT';
    return {
      approverId: seed.approverId ?? null,
      pgOutcome: seed.pgOutcome ?? 'PENDING',
      refund: {
        refundId: rid(seed.n),
        refundNo: `R20264-${String(seed.n).padStart(6, '0')}`,
        applicationNo: seed.applicationNo,
        courseName: payment.courseName,
        requestedAmount: seed.amount,
        status: seed.status,
        receivedOn: seed.received,
        elapsedBusinessDays: seed.elapsed,
        overdue: seed.elapsed > 3 && (seed.status === 'REQUESTED' || seed.status === 'ON_HOLD'),
        requester: seed.requester,
        paymentOrderNo: payment.orderNo,
        paidAmount: payment.paid,
        paymentMethod: payment.method,
        paidAt: payment.paidAt,
        baselineAmount: payment.baseline,
        baselineRule: payment.rule,
        educationStart: payment.educationStart,
        reason: seed.reason,
        detail: null,
        evidenceCount: seed.evidence ?? 0,
        requesterName: seed.requesterName,
        approvedAmount: seed.approved ?? null,
        decisionReason: seed.decisionReason ?? null,
        decidedBy: seed.approverName ?? (seed.status === 'REJECTED' || seed.status === 'ON_HOLD' ? '박정산' : null),
        executionMethod: method,
        manualAccount: method === 'MANUAL_TRANSFER' ? { bankName: '국민은행', holderMasked: '김○○', accountMasked: '123-****-**89' } : null,
        executedBy: seed.executedBy ?? null,
        executionResult: seed.result ?? null,
        history: seed.history.map(([at, status, actor, note]) => ({ at, status, actor, note })),
        version: 1,
      },
    };
  });
}

interface State {
  rows: Row[];
  seq: number;
  idempotent: Map<string, { fingerprint: string; body: Refund }>;
}

let state: State = { rows: initialState(), seq: 20, idempotent: new Map() };

/** 시험 사이에 환불 건을 처음 상태로 되돌린다. */
export function resetMockRefunds(): void {
  state = { rows: initialState(), seq: 20, idempotent: new Map() };
}

const reservedOthers = (row: Row) =>
  state.rows
    .filter((other) => other !== row && other.refund.paymentOrderNo === row.refund.paymentOrderNo && RESERVED.includes(other.refund.status))
    .reduce((sum, other) => sum + (other.refund.approvedAmount ?? other.refund.requestedAmount), 0);

function view(row: Row): Refund {
  const authorities = currentAuthorities();
  const reserved = reservedOthers(row);
  const executable = (row.refund.status === 'APPROVED' || row.refund.status === 'FAILED') && authorities.includes('AU.RFND_X');
  const sameAsApprover = row.approverId !== null && row.approverId === currentAdminId();
  return {
    ...row.refund,
    evidenceCount: row.refund.evidenceCount + countOwnerFiles(`/refunds/${row.refund.refundId}`),
    reservedAmount: reserved,
    remainingAmount: row.refund.paidAmount - reserved,
    canReview: authorities.includes('AU.RFND_A') && (row.refund.status === 'REQUESTED' || row.refund.status === 'ON_HOLD'),
    canExecute: executable && !sameAsApprover,
    canConfirmTransfer: authorities.includes('AU.RFND_X') && row.refund.status === 'PENDING' && row.refund.executionMethod === 'MANUAL_TRANSFER',
    executeNote: executable && sameAsApprover ? '승인한 담당자는 같은 환불 건을 집행할 수 없습니다. 다른 집행 담당자가 처리해 주세요.' : null,
  };
}

const toSummary = (row: Row): Schemas['AdminRefundSummary'] => {
  const r = row.refund;
  return { refundId: r.refundId, refundNo: r.refundNo, applicationNo: r.applicationNo, courseName: r.courseName, requestedAmount: r.requestedAmount, status: r.status, receivedOn: r.receivedOn, elapsedBusinessDays: r.elapsedBusinessDays, overdue: r.overdue, requester: r.requester };
};

const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
const find = (id: unknown) => state.rows.find((row) => row.refund.refundId === id);
// 증빙은 접수·보류 상태에서만 더하거나 지울 수 있다.
registerOwnerInfo('refunds', (id) => {
  const row = find(id);
  return row ? { label: row.refund.refundNo, locked: row.refund.status !== 'REQUESTED' && row.refund.status !== 'ON_HOLD' } : null;
});
const limitExceeded = (field: string) => apiError('RFND_LIMIT_EXCEEDED', { [field]: '환불 가능 금액을 초과합니다.' });

function transition(row: Row, status: Status, note: string | null, actor = currentAdminName()) {
  row.refund.status = status;
  row.refund.version += 1;
  row.refund.history.push({ at: new Date().toISOString(), status, actor, note });
}

/** 공통 검사. 권한·CSRF·존재·버전을 한 번에 본다. 통과하면 행을 돌려주고 아니면 응답을 돌려준다. */
function guard(request: Request, id: unknown, authority: 'AU.RFND_A' | 'AU.RFND_X', version: number) {
  const denied = denyCsrf(request) ?? denyUnless(authority);
  if (denied) return { error: denied };
  const row = find(id);
  if (!row) return { error: apiError('NOT_FOUND') };
  if (version !== row.refund.version) return { error: apiError('VERSION_CONFLICT') };
  return { row };
}

function filteredRefunds(params: URLSearchParams): Row[] {
  const from = params.get('from');
  const to = params.get('to');
  const open = (row: Row) => row.refund.status === 'REQUESTED' || row.refund.status === 'ON_HOLD';
  return state.rows
    .filter(
      (row) =>
        (!params.get('status') || row.refund.status === params.get('status')) &&
        (!params.get('requester') || row.refund.requester === params.get('requester')) &&
        (!from || row.refund.receivedOn >= from) &&
        (!to || row.refund.receivedOn <= to),
    )
    // 검토가 급한 건(접수·보류)을 먼저, 오래된 것부터 보이고 나머지는 최근 접수가 앞이다.
    .sort((a, b) => Number(open(b)) - Number(open(a)) || (open(a) ? a.refund.receivedOn.localeCompare(b.refund.receivedOn) : b.refund.receivedOn.localeCompare(a.refund.receivedOn)));
}

export const refundHandlers = [
  // 환불 계좌 같은 민감 값은 담지 않는다
  http.get('/api/admin/v1/refunds/export.csv', ({ request }) => {
    const denied = denyUnless('AU.RFND_A', 'AU.RFND_X');
    if (denied) return denied;
    const rows = filteredRefunds(new URL(request.url).searchParams).map(({ refund: r }) => [
      r.refundNo, r.applicationNo, r.courseName, r.requestedAmount, r.status, r.requester, r.receivedOn, r.elapsedBusinessDays, r.overdue ? '기한 초과' : '',
    ]);
    return csvResponse('refunds.csv', ['환불번호', '신청번호', '강좌', '신청금액', '상태', '접수 주체', '접수일', '경과 영업일', '기한'], rows);
  }),

  http.get('/api/admin/v1/refunds', ({ request }) => {
    const denied = denyUnless('AU.RFND_A', 'AU.RFND_X');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const rows = filteredRefunds(params);
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size).map(toSummary), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.post('/api/admin/v1/refunds', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.RFND_A');
    if (denied) return denied;
    const body = (await request.json()) as Schemas['AdminRefundCreate'];
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(found.body, { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
    const payment = PAYMENTS[body.applicationNo.trim()];
    if (!payment) return apiError('RULE_REJECTED', { applicationNo: '결제완료된 신청번호를 확인해 주세요.' });
    const reserved = state.rows.filter((row) => row.refund.paymentOrderNo === payment.orderNo && RESERVED.includes(row.refund.status)).reduce((sum, row) => sum + (row.refund.approvedAmount ?? row.refund.requestedAmount), 0);
    if (reserved + body.requestedAmount > payment.paid) return limitExceeded('requestedAmount');
    state.seq += 1;
    const now = new Date().toISOString();
    const created: Row = {
      approverId: null,
      pgOutcome: 'PENDING',
      refund: {
        refundId: rid(state.seq), refundNo: `R20264-${String(state.seq).padStart(6, '0')}`, applicationNo: body.applicationNo.trim(), courseName: payment.courseName,
        requestedAmount: body.requestedAmount, status: 'REQUESTED', receivedOn: today(), elapsedBusinessDays: 0, overdue: false, requester: 'ADMIN',
        paymentOrderNo: payment.orderNo, paidAmount: payment.paid, paymentMethod: payment.method, paidAt: payment.paidAt, baselineAmount: payment.baseline,
        baselineRule: payment.rule, educationStart: payment.educationStart, reason: body.reason.trim(), detail: body.detail?.trim() || null, evidenceCount: 0,
        requesterName: currentAdminName(), approvedAmount: null, decisionReason: null, decidedBy: null, executionMethod: 'CANCEL_PAYMENT', manualAccount: null,
        executedBy: null, executionResult: null, history: [{ at: now, status: 'REQUESTED', actor: currentAdminName(), note: '방문·유선 접수' }], version: 1,
      },
    };
    state.rows.push(created);
    const result = view(created);
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: result });
    return HttpResponse.json(result, { status: 201 });
  }),

  http.get('/api/admin/v1/refunds/:refundId', ({ params }) => {
    const denied = denyUnless('AU.RFND_A', 'AU.RFND_X');
    if (denied) return denied;
    const row = find(params.refundId);
    return row ? HttpResponse.json(view(row)) : apiError('NOT_FOUND');
  }),

  http.put('/api/admin/v1/refunds/:refundId/hold', async ({ request, params }) => {
    const { reason, version } = (await request.json()) as Schemas['RefundHoldRequest'];
    const checked = guard(request, params.refundId, 'AU.RFND_A', version);
    if (checked.error) return checked.error;
    const row = checked.row!;
    if (row.refund.status !== 'REQUESTED') return apiError('CONFLICT_STATE');
    row.refund.decisionReason = reason.trim();
    row.refund.decidedBy = currentAdminName();
    transition(row, 'ON_HOLD', reason.trim());
    return HttpResponse.json(view(row));
  }),

  http.post('/api/admin/v1/refunds/:refundId/release-hold', async ({ request, params }) => {
    const { version } = (await request.json()) as Schemas['RefundVersionRequest'];
    const checked = guard(request, params.refundId, 'AU.RFND_A', version);
    if (checked.error) return checked.error;
    const row = checked.row!;
    if (row.refund.status !== 'ON_HOLD') return apiError('CONFLICT_STATE');
    row.refund.decisionReason = null;
    transition(row, 'REQUESTED', '보류 해제');
    return HttpResponse.json(view(row));
  }),

  http.put('/api/admin/v1/refunds/:refundId/approve', async ({ request, params }) => {
    const { amount, version } = (await request.json()) as Schemas['RefundApproveRequest'];
    const checked = guard(request, params.refundId, 'AU.RFND_A', version);
    if (checked.error) return checked.error;
    const row = checked.row!;
    if (row.refund.status !== 'REQUESTED') return apiError('CONFLICT_STATE');
    // 원결제 행을 잠근 상태에서 완료·승인·처리중 예약액을 합쳐 확정 검사한다(FN-045).
    if (reservedOthers(row) + amount > row.refund.paidAmount) return limitExceeded('amount');
    row.refund.approvedAmount = amount;
    row.refund.decidedBy = currentAdminName();
    row.approverId = currentAdminId();
    transition(row, 'APPROVED', `승인액 ${amount.toLocaleString('ko-KR')}원`);
    return HttpResponse.json(view(row));
  }),

  http.put('/api/admin/v1/refunds/:refundId/reject', async ({ request, params }) => {
    const { reason, version } = (await request.json()) as Schemas['RefundRejectRequest'];
    const checked = guard(request, params.refundId, 'AU.RFND_A', version);
    if (checked.error) return checked.error;
    const row = checked.row!;
    if (row.refund.status !== 'REQUESTED') return apiError('CONFLICT_STATE');
    row.refund.decisionReason = reason.trim();
    row.refund.decidedBy = currentAdminName();
    transition(row, 'REJECTED', reason.trim());
    return HttpResponse.json(view(row));
  }),

  http.post('/api/admin/v1/refunds/:refundId/execute', async ({ request, params }) => {
    const { version } = (await request.json()) as Schemas['RefundVersionRequest'];
    const checked = guard(request, params.refundId, 'AU.RFND_X', version);
    if (checked.error) return checked.error;
    const row = checked.row!;
    if (row.refund.status !== 'APPROVED' && row.refund.status !== 'FAILED') return apiError('CONFLICT_STATE');
    // 승인과 집행은 다른 담당자가 한다(PRD Q22 임시 기준).
    if (row.approverId === currentAdminId()) return apiError('RULE_REJECTED', { executor: '승인한 담당자는 같은 환불 건을 집행할 수 없습니다.' });
    // 재처리도 같은 한도 검사를 다시 한다.
    if (reservedOthers(row) + (row.refund.approvedAmount ?? 0) > row.refund.paidAmount) return limitExceeded('amount');
    row.refund.executedBy = currentAdminName();
    if (row.refund.executionMethod === 'MANUAL_TRANSFER') {
      row.refund.executionResult = '이체 대기 중입니다.';
      transition(row, 'PENDING', '집행 요청(수동 계좌환불)');
    } else if (row.pgOutcome === 'DONE') {
      row.refund.executionResult = '원결제가 취소되었습니다.';
      transition(row, 'DONE', 'PG 취소 확인');
    } else if (row.pgOutcome === 'FAILED') {
      row.refund.executionResult = 'PG 취소 요청이 실패했습니다.';
      row.pgOutcome = 'DONE'; // 재처리하면 성공하도록 한다.
      transition(row, 'FAILED', 'PG 취소 요청 실패');
    } else {
      row.refund.executionResult = 'PG 결과를 확인하는 중입니다.';
      transition(row, 'PENDING', '집행 요청(원결제 취소)');
    }
    return HttpResponse.json(view(row));
  }),

  http.post('/api/admin/v1/refunds/:refundId/confirm-done', async ({ request, params }) => {
    const { version } = (await request.json()) as Schemas['RefundVersionRequest'];
    const checked = guard(request, params.refundId, 'AU.RFND_X', version);
    if (checked.error) return checked.error;
    const row = checked.row!;
    if (row.refund.status !== 'PENDING' || row.refund.executionMethod !== 'MANUAL_TRANSFER') return apiError('CONFLICT_STATE');
    row.refund.executionResult = '이체가 완료되었습니다.';
    transition(row, 'DONE', '이체 완료 확인');
    return HttpResponse.json(view(row));
  }),
];