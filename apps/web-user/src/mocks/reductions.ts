// 회원의 감면 사전심사를 흉내 내는 모의 서버. 같은 기수에 접수·승인 건이 있으면 새로 신청할 수 없고 증빙은 접수 상태에서만 바꾼다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, csrfRejected, currentMockMember } from './auth';
import { countFiles, registerOwnerInfo, seedFile } from './files';

type Review = Schemas['MyReduction'];
type Type = Schemas['ReductionType'];

const DEMO_ID = '1000000000000000000001';
const CYCLES = [
  { id: '1000000000000000000001', name: '2026년 제4기' },
  { id: '1000000000000000000002', name: '2027년 제1기' },
];
const TYPES: Type[] = ['LIVELIHOOD', 'VETERAN', 'DISABLED'];

interface Stored {
  memberId: string;
  cycleId: string;
  review: Omit<Review, 'evidenceCount' | 'canAddEvidence' | 'canWithdraw'>;
}
interface State {
  items: Map<string, Stored>;
  keys: Map<string, string>;
  seq: number;
}

const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
const nameOf = (cycleId: string) => CYCLES.find((item) => item.id === cycleId)?.name ?? '';
const rid = (n: number) => `50${String(n).padStart(2, '0')}`;
const ownerPath = (id: string) => `/me/reduction-reviews/${id}`;

function initialState(): State {
  const items = new Map<string, Stored>();
  items.set('5001', { memberId: DEMO_ID, cycleId: CYCLES[0]!.id, review: { reviewId: '5001', cycleName: nameOf(CYCLES[0]!.id), reductionType: 'LIVELIHOOD', status: 'REJECTED', appliedOn: '2026-09-01', validUntil: null, rejectReason: '증빙 서류가 확인되지 않습니다.' } });
  items.set('5002', { memberId: DEMO_ID, cycleId: CYCLES[1]!.id, review: { reviewId: '5002', cycleName: nameOf(CYCLES[1]!.id), reductionType: 'VETERAN', status: 'APPROVED', appliedOn: '2026-09-02', validUntil: '2030-12-31', rejectReason: null } });
  return { items, keys: new Map(), seq: 2 };
}

let state = initialState();

function seedEvidence(): void {
  seedFile(ownerPath('5001'), DEMO_ID, '증명서.pdf');
  seedFile(ownerPath('5002'), DEMO_ID, '유공자 증서.pdf');
}
seedEvidence();

/** 시험 사이에 감면 심사를 처음 상태로 되돌린다. 증빙 파일은 파일 모의 서버를 먼저 비운 뒤 다시 붙인다. */
export function resetMockReductions(): void {
  state = initialState();
  seedEvidence();
}

// 증빙은 접수 상태에서만 더하거나 지울 수 있다. 남의 신청은 null이다.
registerOwnerInfo('reduction-reviews', (id, memberId) => {
  const found = state.items.get(id);
  return found && found.memberId === memberId ? { locked: found.review.status !== 'RECEIVED' } : null;
});

const present = (stored: Stored): Review => ({
  ...stored.review,
  evidenceCount: countFiles(ownerPath(stored.review.reviewId)),
  canAddEvidence: stored.review.status === 'RECEIVED',
  canWithdraw: stored.review.status === 'RECEIVED',
});
const mine = (memberId: string) => [...state.items.values()].filter((item) => item.memberId === memberId);
const summary = (review: Review): Schemas['MyReductionSummary'] => ({ reviewId: review.reviewId, cycleName: review.cycleName, reductionType: review.reductionType, status: review.status, appliedOn: review.appliedOn, evidenceCount: review.evidenceCount });

export const reductionHandlers = [
  http.get('/api/v1/me/reduction-options', () => {
    if (!currentMockMember()) return apiError('UNAUTHENTICATED');
    return HttpResponse.json({ cycles: CYCLES, canApply: true, blockReason: null } satisfies Schemas['MyReductionOptions']);
  }),

  http.get('/api/v1/me/reduction-reviews', () => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const items = mine(member.memberId)
      .map(present)
      .sort((a, b) => b.appliedOn.localeCompare(a.appliedOn) || b.reviewId.localeCompare(a.reviewId))
      .map(summary);
    return HttpResponse.json({ items } satisfies Schemas['MyReductionList']);
  }),

  http.post('/api/v1/me/reduction-reviews', async ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const key = request.headers.get('Idempotency-Key');
    if (!key) return apiError('VALIDATION_FAILED', { 'Idempotency-Key': '멱등키가 필요합니다.' });
    const known = state.keys.get(key);
    if (known) return HttpResponse.json(present(state.items.get(known)!), { status: 201 });
    const body = (await request.json()) as Schemas['MyReductionCreate'];
    if (!TYPES.includes(body.reductionType)) return apiError('VALIDATION_FAILED', { reductionType: '감면 유형을 확인해 주세요.' });
    if (!nameOf(body.cycleId)) return apiError('VALIDATION_FAILED', { cycleId: '교육기수를 확인해 주세요.' });
    if (mine(member.memberId).some((item) => item.cycleId === body.cycleId && (item.review.status === 'RECEIVED' || item.review.status === 'APPROVED'))) {
      return apiError('RULE_REJECTED', { cycleId: '이 기수에는 이미 접수되었거나 승인된 심사가 있습니다.' });
    }
    state.seq += 1;
    const review = { reviewId: rid(state.seq), cycleName: nameOf(body.cycleId), reductionType: body.reductionType, status: 'RECEIVED' as const, appliedOn: today(), validUntil: null, rejectReason: null };
    const stored: Stored = { memberId: member.memberId, cycleId: body.cycleId, review };
    state.items.set(review.reviewId, stored);
    state.keys.set(key, review.reviewId);
    return HttpResponse.json(present(stored), { status: 201 });
  }),

  http.get('/api/v1/me/reduction-reviews/:reviewId', ({ params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const found = state.items.get(String(params.reviewId));
    return found && found.memberId === member.memberId ? HttpResponse.json(present(found)) : apiError('NOT_FOUND');
  }),

  http.post('/api/v1/me/reduction-reviews/:reviewId/withdraw', ({ request, params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const found = state.items.get(String(params.reviewId));
    if (!found || found.memberId !== member.memberId) return apiError('NOT_FOUND');
    if (found.review.status !== 'RECEIVED') return apiError('CONFLICT_STATE');
    found.review.status = 'REVOKED';
    return HttpResponse.json(present(found));
  }),
];