// 이름 변경 요청 검토를 흉내 내는 모의 서버. 검토 중인 요청만 승인·반려하고 승인하면 현재 이름이 새 이름으로 바뀐다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, denyCsrf, denyUnless } from './auth';

type Item = Schemas['AdminNameChange'];

const nid = (n: number) => `94${String(n).padStart(20, '0')}`;

function initialState(): Item[] {
  const base = { reason: '개명 판결문 확인 예정', decisionNote: null, decidedAt: null, decidedBy: null, state: 'PENDING' as const };
  return [
    { ...base, requestId: nid(1), memberId: '3000000000000000000001', loginId: 'kim01', currentNameMasked: '김*원', requestedName: '김새롬', requestedAt: '2026-11-10T01:00:00Z' },
    { ...base, requestId: nid(2), memberId: '3000000000000000000002', loginId: 'park02', currentNameMasked: '박*라', requestedName: '박다온', reason: '호적 정정으로 이름이 바뀌었습니다.', requestedAt: '2026-11-12T02:00:00Z' },
    { ...base, requestId: nid(3), memberId: '3000000000000000000003', loginId: 'lee03', currentNameMasked: '이*름', requestedName: '이하늘', requestedAt: '2026-11-01T01:00:00Z', state: 'APPROVED', decidedAt: '2026-11-02T01:00:00Z', decidedBy: '김관리', decisionNote: '판결문 확인' },
  ];
}

let state = initialState();

/** 시험 사이에 이름 변경 요청을 처음 상태로 되돌린다. */
export function resetMockNameChanges(): void {
  state = initialState();
}

export const nameChangeHandlers = [
  http.get('/api/admin/v1/name-change-requests', ({ request }) => {
    const denied = denyUnless('AU.GRANT_W');
    if (denied) return denied;
    const decided = new URL(request.url).searchParams.get('state') === 'DECIDED';
    const items = state.filter((item) => (item.state !== 'PENDING') === decided);
    const byRequested = [...items].sort((a, b) => a.requestedAt.localeCompare(b.requestedAt)); // 검토 중은 오래된 순, 처리한 요청은 최근 순
    return HttpResponse.json({ items: decided ? byRequested.reverse() : byRequested } satisfies Schemas['AdminNameChangeList']);
  }),

  ...(['approve', 'reject'] as const).map((action) =>
    http.post(`/api/admin/v1/name-change-requests/:requestId/${action}`, async ({ request, params }) => {
      const denied = denyCsrf(request) ?? denyUnless('AU.GRANT_W');
      if (denied) return denied;
      const found = state.find((item) => item.requestId === params.requestId);
      if (!found) return apiError('NOT_FOUND');
      if (found.state !== 'PENDING') return apiError('CONFLICT_STATE');
      const body = (await request.json()) as Schemas['NameChangeDecide'];
      found.state = action === 'approve' ? 'APPROVED' : 'REJECTED';
      found.decidedAt = new Date().toISOString();
      found.decidedBy = currentAdminName();
      found.decisionNote = body.note ?? null;
      if (action === 'approve') found.currentNameMasked = `${found.requestedName[0]}*${found.requestedName.slice(2)}`;
      return HttpResponse.json(found);
    }),
  ),
];
