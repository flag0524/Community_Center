// 관리자 보존·파기 검토를 흉내 내는 모의 서버. 실행은 예정일이 지난 자료만, 확인한 건수가 같을 때만 처리한다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, currentAuthorities, denyCsrf, denyUnless } from './auth';

type Item = Schemas['RetentionItem'];

const rid = (n: number) => `92${String(n).padStart(20, '0')}`;

interface Stored {
  item: Item;
  rule: string;
  fields: string[];
  executions: Schemas['RetentionExecution'][];
}
interface State {
  rows: Stored[];
  idempotent: Map<string, { fingerprint: string; body: Schemas['RetentionDetail'] }>;
}

function initialState(): State {
  const row = (n: number, target: Item['target'], count: number, baseDate: string | null, dueOn: string | null, state: Item['state'], rule: string, fields: string[]): Stored => ({
    item: { itemId: rid(n), target, count, baseDate, dueOn, state }, rule, fields, executions: [],
  });
  return {
    rows: [
      row(1, 'WITHDRAWN_MEMBER', 3, '2026-10-05', '2026-11-04', 'DUE', '탈퇴 후 30일이 지난 회원의 일반 개인정보를 비식별 처리합니다. 결제·환불 원장은 탈퇴와 관계없이 보존합니다.', ['이름', '휴대전화', '이메일']),
      row(2, 'AUTH_RECORDS', 140, '2026-10-01', '2026-10-31', 'DUE', '만료된 인증 기록을 정리합니다. 보존기간은 가정값이며 기관 확인이 필요합니다(PRD Q30).', ['OTP 요청', '로그인 세션', '로그인 실패 이력']),
      row(3, 'AUDIT_HISTORY', 12, '2023-11-01', '2026-11-01', 'REVIEW_ONLY', '업무 감사이력은 3년 보존하며 이 화면에서는 보존기간이 지난 목록을 검토만 합니다.', ['감사이력(조회 전용)']),
      row(4, 'REFUND_ACCOUNT', 5, null, null, 'PERIOD_TBD', '환불 집행이 끝난 수동환불 계좌정보의 보존기간이 정해지지 않았습니다. 정해지기 전에는 파기하지 않습니다.', ['수동환불 계좌정보']),
      row(5, 'SMS_RECORDS', 40, null, null, 'PERIOD_TBD', '문자 문안과 수신명단의 보존기간이 정해지지 않았습니다. 정해지기 전에는 파기하지 않습니다.', ['문안', '수신 명단']),
    ],
    idempotent: new Map(),
  };
}

let state = initialState();

/** 시험 사이에 보존 목록을 처음 상태로 되돌린다. */
export function resetMockRetention(): void {
  state = initialState();
}

const detail = (stored: Stored): Schemas['RetentionDetail'] => ({
  ...stored.item, rule: stored.rule, fields: stored.fields, executions: [...stored.executions].reverse(),
  canExecute: stored.item.state === 'DUE' && stored.item.count > 0 && currentAuthorities().includes('AU.GRANT_W'),
});

export const retentionHandlers = [
  http.get('/api/admin/v1/retention', () => {
    const denied = denyUnless('AU.LOG_R');
    if (denied) return denied;
    return HttpResponse.json({
      items: state.rows.map((stored) => stored.item),
      exclusions: [{ label: '정산자료(결제·환불 원장)', reason: '법정 보존 5년 대상이라 탈퇴와 관계없이 파기하지 않습니다.' }],
    } satisfies Schemas['RetentionList']);
  }),

  http.get('/api/admin/v1/retention/:itemId', ({ params }) => {
    const denied = denyUnless('AU.LOG_R');
    if (denied) return denied;
    const stored = state.rows.find((row) => row.item.itemId === params.itemId);
    return stored ? HttpResponse.json(detail(stored)) : apiError('NOT_FOUND');
  }),

  http.post('/api/admin/v1/retention/:itemId/execute', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.GRANT_W');
    if (denied) return denied;
    const body = (await request.json()) as Schemas['RetentionExecute'];
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(found.body) : apiError('IDEMPOTENCY_CONFLICT');
    const stored = state.rows.find((row) => row.item.itemId === params.itemId);
    if (!stored) return apiError('NOT_FOUND');
    if (stored.item.state !== 'DUE') return apiError('RULE_REJECTED', { itemId: '예정일이 지난 자료만 실행할 수 있습니다.' });
    if (stored.item.count !== body.expectedCount) return apiError('CONFLICT_STATE', { expectedCount: `대상이 바뀌었습니다. 현재 ${stored.item.count}건입니다.` });
    stored.executions.push({ at: new Date().toISOString(), by: currentAdminName(), processed: stored.item.count });
    stored.item.count = 0;
    const result = detail(stored);
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: result });
    return HttpResponse.json(result);
  }),
];