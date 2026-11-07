// 관리자 감면 사전심사를 흉내 내는 모의 서버. 결정한 심사는 고치지 않고 재심사로 새 건을 만든다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, currentAuthorities, denyCsrf, denyUnless } from './auth';
import { registerFileResolver } from './files';

type Review = Schemas['ReductionReview'];

const rid = (n: number) => `80${String(n).padStart(20, '0')}`;
const fid = (n: number) => `81${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;

interface State {
  rows: Review[];
  seq: number;
  idempotent: Map<string, Review>;
}

function initialState(): State {
  const file = (n: number, fileName: string, status: Schemas['FileStatus'] = 'SAFE'): Schemas['ReductionEvidence'] => ({ fileId: fid(n), fileName, sizeBytes: 524_288, status });
  const base = (n: number, memberName: string, type: Schemas['ReductionType'], appliedOn: string, status: Schemas['ReductionStatus'], evidence: Schemas['ReductionEvidence'][], extra: Partial<Review> = {}): Review => ({
    reviewId: rid(n), memberName, cycleName: '2026년 제4기', reductionType: type, evidenceCount: evidence.length, appliedOn, status, residenceConfirmed: true, evidence, evidenceViews: [],
    reviewedBy: null, reviewedAt: null, reviewNote: null, rejectReason: null, validUntil: null, version: 1, canDecide: false, canReReview: false, canViewEvidence: false, ...extra,
  });
  return {
    rows: [
      base(1, '김○○', 'LIVELIHOOD', '2026-10-20', 'RECEIVED', [file(1, '수급자 증명서.pdf'), file(2, '가족관계증명서.pdf', 'PENDING')]),
      base(2, '이○○', 'VETERAN', '2026-10-22', 'RECEIVED', [file(3, '유공자 증서.pdf')], { residenceConfirmed: false }),
      base(3, '박○○', 'DISABLED', '2026-10-15', 'APPROVED', [file(4, '장애인 등록증.jpg')], { reviewedBy: '김관리', reviewedAt: '2026-10-16T10:00:00+09:00', reviewNote: '증빙 확인', validUntil: '2030-12-31', version: 2 }),
      base(4, '최○○', 'LIVELIHOOD', '2026-10-10', 'REJECTED', [file(5, '증명서.pdf')], { reviewedBy: '김관리', reviewedAt: '2026-10-12T10:00:00+09:00', rejectReason: '증빙 서류가 확인되지 않습니다.', version: 2 }),
    ],
    seq: 20,
    idempotent: new Map(),
  };
}

let state = initialState();

// 증빙은 파일 내려받기로 열람한다. 내려받으면 열람자와 시각이 열람 기록에 남는다(비공개 파일).
registerFileResolver((fileId) => {
  for (const review of state.rows) {
    const file = review.evidence.find((item) => item.fileId === fileId);
    if (file) return { authority: 'AU.APLY_W', status: file.status, fileName: file.fileName, onDownload: (by) => review.evidenceViews.push({ at: new Date().toISOString(), by, fileName: file.fileName }) };
  }
  return undefined;
});

/** 시험 사이에 감면 심사를 처음 상태로 되돌린다. */
export function resetMockReductions(): void {
  state = initialState();
}

const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
const summary = (r: Review): Schemas['ReductionReviewSummary'] => ({ reviewId: r.reviewId, memberName: r.memberName, cycleName: r.cycleName, reductionType: r.reductionType, evidenceCount: r.evidenceCount, appliedOn: r.appliedOn, status: r.status });
// 심사 권한은 후보 권한 AU.APLY_W로 판정한다(PRD Q21).
const flags = (r: Review): Review => {
  const reviewer = currentAuthorities().includes('AU.APLY_W');
  return { ...r, canDecide: reviewer && r.status === 'RECEIVED', canReReview: reviewer && (r.status === 'APPROVED' || r.status === 'REJECTED'), canViewEvidence: reviewer };
};

const HISTORY: Schemas['ReductionHistoryRow'][] = [
  { historyId: '8200000000000000000001', decidedAt: '2026-10-25T10:00:00+09:00', memberName: '박○○', cycleName: '2026년 제4기', result: 'APPROVE', amount: 30000, reason: '사전심사 승인 적용', decidedBy: '김관리', evidenceCount: 1, applicationNo: 'A20264-000101' },
  { historyId: '8200000000000000000002', decidedAt: '2026-10-21T14:30:00+09:00', memberName: '최○○', cycleName: '2026년 제4기', result: 'REJECT', amount: null, reason: '증빙 부족', decidedBy: '김관리', evidenceCount: 1, applicationNo: null },
];

export const reductionHandlers = [
  http.get('/api/admin/v1/reductions', ({ request }) => {
    const denied = denyUnless('AU.APLY_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const status = params.get('status');
    const rows = state.rows
      .filter((row) => !status || row.status === status)
      .sort((a, b) => Number(b.status === 'RECEIVED') - Number(a.status === 'RECEIVED') || (a.status === 'RECEIVED' ? a.appliedOn.localeCompare(b.appliedOn) : b.appliedOn.localeCompare(a.appliedOn)) || a.reviewId.localeCompare(b.reviewId));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size).map(summary), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.get('/api/admin/v1/reductions/:reviewId', ({ params }) => {
    const denied = denyUnless('AU.APLY_R');
    if (denied) return denied;
    const row = state.rows.find((item) => item.reviewId === params.reviewId);
    return row ? HttpResponse.json(flags(row)) : apiError('NOT_FOUND');
  }),

  http.post('/api/admin/v1/reductions/:reviewId/decision', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.APLY_W');
    if (denied) return denied;
    const row = state.rows.find((item) => item.reviewId === params.reviewId);
    if (!row) return apiError('NOT_FOUND');
    const body = (await request.json()) as Schemas['ReductionDecisionRequest'];
    if (body.version !== row.version) return apiError('VERSION_CONFLICT');
    if (row.status !== 'RECEIVED') return apiError('CONFLICT_STATE');
    const fields: Record<string, string> = {};
    if (body.decision === 'APPROVE') {
      if (!row.residenceConfirmed) fields.decision = '조리읍 거주 확인이 된 회원만 승인할 수 있습니다.';
      if (!body.validUntil) fields.validUntil = '승인 유효 종료일을 입력해 주세요.';
      else if (body.validUntil <= today()) fields.validUntil = '유효 종료일은 오늘 이후여야 합니다.';
    } else if (!body.rejectReason?.trim()) fields.rejectReason = '반려 사유를 입력해 주세요.';
    if (Object.keys(fields).length > 0) return apiError('RULE_REJECTED', fields);
    Object.assign(row, {
      status: body.decision === 'APPROVE' ? 'APPROVED' : 'REJECTED',
      reviewedBy: currentAdminName(),
      reviewedAt: new Date().toISOString(),
      reviewNote: body.reviewNote?.trim() || null,
      rejectReason: body.decision === 'REJECT' ? body.rejectReason!.trim() : null,
      validUntil: body.decision === 'APPROVE' ? body.validUntil! : null,
      version: row.version + 1,
    });
    return HttpResponse.json(flags(row));
  }),

  http.post('/api/admin/v1/reductions/:reviewId/re-review', ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.APLY_W');
    if (denied) return denied;
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return HttpResponse.json(flags(found), { status: 201 });
    const row = state.rows.find((item) => item.reviewId === params.reviewId);
    if (!row) return apiError('NOT_FOUND');
    if (row.status !== 'APPROVED' && row.status !== 'REJECTED') return apiError('CONFLICT_STATE');
    state.seq += 1;
    const created: Review = { ...row, reviewId: rid(state.seq), appliedOn: today(), status: 'RECEIVED', evidence: [], evidenceCount: 0, evidenceViews: [], reviewedBy: null, reviewedAt: null, reviewNote: null, rejectReason: null, validUntil: null, version: 1 };
    state.rows.push(created);
    if (key) state.idempotent.set(key, created);
    return HttpResponse.json(flags(created), { status: 201 });
  }),

  http.get('/api/admin/v1/reduction-history', ({ request }) => {
    const denied = denyUnless('AU.APLY_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const result = params.get('result');
    const from = params.get('from');
    const to = params.get('to');
    const rows = HISTORY.filter((row) => (!result || row.result === result) && (!from || row.decidedAt.slice(0, 10) >= from) && (!to || row.decidedAt.slice(0, 10) <= to)).sort((a, b) => b.decidedAt.localeCompare(a.decidedAt));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),
];