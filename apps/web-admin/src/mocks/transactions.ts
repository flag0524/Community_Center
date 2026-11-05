// 관리자 결제·거래 대조를 흉내 내는 모의 서버. PG 재조회와 수동 대사는 결과 확인 중인 거래에만 하고 근거·승인번호를 서버가 검사한다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, currentAuthorities, denyCsrf, denyUnless } from './auth';

type Transaction = Schemas['Transaction'];

const txnId = (n: number) => `13${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;

interface Seed {
  applicationNo: string;
  courseName: string;
  applicantName: string;
  state: Transaction['applicationState'];
  method: Transaction['method'];
  amount: number;
  status: Transaction['status'];
  requestedAt: string;
  approvedAt: string | null;
  recheckCount: number;
  notices: Transaction['notices'];
  refund?: Transaction['refund'];
  /** 재조회하면 PG가 이 결과를 돌려준다. null이면 계속 알 수 없다. */
  pgResolvesPaid: boolean;
}

const SEEDS: Seed[] = [
  { applicationNo: 'A20264-000201', courseName: '초급컴퓨터', applicantName: '김○○', state: 'CONFIRMED', method: 'CARD', amount: 60000, status: 'PAID', requestedAt: '2026-09-07T09:00:30+09:00', approvedAt: '2026-09-07T09:03:00+09:00', recheckCount: 0, notices: [{ at: '2026-09-07T09:03:02+09:00', hashPrefix: 'c3d4', handling: 'DONE' }], pgResolvesPaid: false },
  {
    applicationNo: 'A20264-000203', courseName: '초급컴퓨터', applicantName: '박○○', state: 'PAYMENT_UNKNOWN', method: 'CARD', amount: 60000, status: 'PENDING', requestedAt: '2026-09-07T10:01:12+09:00', approvedAt: null, recheckCount: 3,
    notices: [
      { at: '2026-09-07T10:01:40+09:00', hashPrefix: 'a1b2', handling: 'DONE' },
      { at: '2026-09-07T10:01:41+09:00', hashPrefix: 'a1b2', handling: 'DUPLICATE' },
      { at: '2026-09-07T10:02:05+09:00', hashPrefix: 'ff09', handling: 'CONFLICT' },
    ],
    pgResolvesPaid: false,
  },
  { applicationNo: 'A20264-000301', courseName: '라인댄스 A', applicantName: '허○○', state: 'PAYMENT_UNKNOWN', method: 'TRANSFER', amount: 60000, status: 'PENDING', requestedAt: '2026-09-08T11:20:00+09:00', approvedAt: null, recheckCount: 1, notices: [], pgResolvesPaid: true },
  { applicationNo: 'A20264-000302', courseName: '생활영어', applicantName: '문○○', state: 'PAYMENT_FAILED', method: 'CARD', amount: 60000, status: 'FAILED', requestedAt: '2026-09-08T12:00:00+09:00', approvedAt: null, recheckCount: 0, notices: [], pgResolvesPaid: false },
  { applicationNo: 'A20264-000211', courseName: '요가A(중급)', applicantName: '오○○', state: 'CONFIRMED', method: 'TRANSFER', amount: 60000, status: 'PAID', requestedAt: '2026-09-09T09:30:00+09:00', approvedAt: '2026-09-09T09:32:00+09:00', recheckCount: 0, notices: [], refund: { refundNo: 'R20264-000011', amount: 60000, status: 'REQUESTED' }, pgResolvesPaid: false },
  { applicationNo: 'A20264-000303', courseName: '통기타', applicantName: '배○○', state: 'PAYMENT_UNKNOWN', method: 'CARD', amount: 30000, status: 'PENDING', requestedAt: '2026-09-09T15:00:00+09:00', approvedAt: null, recheckCount: 3, notices: [], pgResolvesPaid: false },
];

interface Row extends Omit<Transaction, 'canRecheck' | 'canReconcile'> {
  pgResolvesPaid: boolean;
}

function initialState(): Row[] {
  return SEEDS.map((seed, index): Row => {
    const n = index + 1;
    return {
      transactionId: txnId(n),
      orderNo: `ORD-20260907-${String(n).padStart(6, '0')}`,
      applicationNo: seed.applicationNo,
      amount: seed.amount,
      method: seed.method,
      status: seed.status,
      requestedAt: seed.requestedAt,
      approvedAt: seed.approvedAt,
      recheckCount: seed.recheckCount,
      hasConflict: seed.notices.some((notice) => notice.handling === 'CONFLICT'),
      applicationId: `12${String(n).padStart(20, '0')}`,
      courseName: seed.courseName,
      applicantName: seed.applicantName,
      applicationState: seed.state,
      merchantId: 'MID-TEST-0001',
      paymentDeadlineAt: seed.status === 'PENDING' ? new Date(new Date(seed.requestedAt).getTime() + 600_000).toISOString() : null,
      recheckMax: 3,
      lastRecheckAt: seed.recheckCount > 0 ? new Date(new Date(seed.requestedAt).getTime() + 360_000).toISOString() : null,
      notices: seed.notices,
      actions: [],
      refund: seed.refund ?? null,
      version: 1,
      pgResolvesPaid: seed.pgResolvesPaid,
    };
  });
}

let state = initialState();

/** 시험 사이에 거래를 처음 상태로 되돌린다. */
export function resetMockTransactions(): void {
  state = initialState();
}

const withFlags = (row: Row): Transaction => {
  const { pgResolvesPaid: _unused, ...rest } = row;
  void _unused;
  const allowed = row.status === 'PENDING' && currentAuthorities().includes('AU.STLM_W');
  return { ...rest, canRecheck: allowed, canReconcile: allowed };
};

const toSummary = (row: Row): Schemas['TransactionSummary'] => ({
  transactionId: row.transactionId,
  orderNo: row.orderNo,
  applicationNo: row.applicationNo,
  amount: row.amount,
  method: row.method,
  status: row.status,
  requestedAt: row.requestedAt,
  approvedAt: row.approvedAt,
  recheckCount: row.recheckCount,
  hasConflict: row.hasConflict,
});

const find = (id: unknown) => state.find((row) => row.transactionId === id);

export const transactionHandlers = [
  http.get('/api/admin/v1/transactions', ({ request }) => {
    const denied = denyUnless('AU.STLM_R', 'AU.STLM_W');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const q = params.get('q')?.trim();
    const from = params.get('from');
    const to = params.get('to');
    const rows = state
      .filter(
        (row) =>
          (!q || row.orderNo.includes(q) || row.applicationNo.includes(q)) &&
          (!params.get('status') || row.status === params.get('status')) &&
          (!params.get('method') || row.method === params.get('method')) &&
          (!from || row.requestedAt.slice(0, 10) >= from) &&
          (!to || row.requestedAt.slice(0, 10) <= to) &&
          (params.get('conflictOnly') !== 'true' || row.hasConflict),
      )
      // 결과 확인 중인 거래를 먼저 보이고 그 안에서는 최근 요청이 앞이다.
      .sort((a, b) => Number(b.status === 'PENDING') - Number(a.status === 'PENDING') || b.requestedAt.localeCompare(a.requestedAt));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size).map(toSummary), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.get('/api/admin/v1/transactions/:transactionId', ({ params }) => {
    const denied = denyUnless('AU.STLM_R', 'AU.STLM_W');
    if (denied) return denied;
    const row = find(params.transactionId);
    return row ? HttpResponse.json(withFlags(row)) : apiError('NOT_FOUND');
  }),

  http.post('/api/admin/v1/transactions/:transactionId/recheck', ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.STLM_W');
    if (denied) return denied;
    const row = find(params.transactionId);
    if (!row) return apiError('NOT_FOUND');
    if (row.status !== 'PENDING') return apiError('CONFLICT_STATE');
    const now = new Date().toISOString();
    // 운영자가 누른 재조회는 자동 재조회 횟수(한도 3회)에 넣지 않는다.
    row.lastRecheckAt = now;
    if (row.pgResolvesPaid) {
      Object.assign(row, { status: 'PAID', approvedAt: now, applicationState: 'CONFIRMED', paymentDeadlineAt: null });
      row.actions.push({ at: now, kind: 'RECHECK', actor: currentAdminName(), result: 'PG에서 승인을 확인했습니다.' });
    } else {
      row.actions.push({ at: now, kind: 'RECHECK', actor: currentAdminName(), result: 'PG가 결과를 알려 주지 않았습니다. 상태는 그대로입니다.' });
    }
    row.version += 1;
    return HttpResponse.json(withFlags(row));
  }),

  http.post('/api/admin/v1/transactions/:transactionId/manual-reconcile', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.STLM_W');
    if (denied) return denied;
    const row = find(params.transactionId);
    if (!row) return apiError('NOT_FOUND');
    const body = (await request.json()) as Schemas['ReconcileRequest'];
    if (row.status !== 'PENDING') return apiError('CONFLICT_STATE');
    if (body.version !== row.version) return apiError('VERSION_CONFLICT');
    const fields: Record<string, string> = {};
    if (body.evidence.trim().length < 5) fields.evidence = '확인 근거를 5자 이상 입력해 주세요.';
    if (body.outcome === 'PAID' && !body.approvalNo?.trim()) fields.approvalNo = '성공으로 처리하려면 PG 승인번호가 필요합니다.';
    if (Object.keys(fields).length > 0) return apiError('RULE_REJECTED', fields);
    const now = new Date().toISOString();
    if (body.outcome === 'PAID') {
      Object.assign(row, { status: 'PAID', approvedAt: now, applicationState: 'CONFIRMED', paymentDeadlineAt: null });
    } else {
      Object.assign(row, { status: 'FAILED', applicationState: 'PAYMENT_FAILED' });
    }
    const label = body.outcome === 'PAID' ? `성공 처리(승인번호 ${body.approvalNo!.trim()})` : '실패 처리';
    row.actions.push({ at: now, kind: 'MANUAL_RECONCILE', actor: currentAdminName(), result: `${label}. 근거: ${body.evidence.trim()}` });
    row.version += 1;
    return HttpResponse.json(withFlags(row));
  }),
];