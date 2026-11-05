// 관리자 회원 조회·검토 기록을 흉내 내는 모의 서버. 회원 정보를 바꾸는 요청은 없고 이름·연락처는 가려서 주며 원문은 사유와 함께 따로 연다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, currentAuthorities, denyCsrf, denyUnless } from './auth';

type Member = Schemas['AdminMember'];

const mid = (n: number) => `15${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;

interface Row {
  member: Omit<Member, 'canReview'>;
  /** 실제 이름과 연락처는 응답에 넣지 않고 검색과 원문 보기에만 쓴다. 모두 지어낸 값이다. */
  realName: string;
  phone: string;
  email: string;
}

interface Seed {
  n: number;
  loginId: string;
  realName: string;
  status: Schemas['MemberStatus'];
  declared: Schemas['ResidenceDeclared'] | null;
  residence: Schemas['ResidenceStatus'];
  joined: string;
  applications: Member['applications'];
  reviews?: Member['reviews'];
}

const SEEDS: Seed[] = [
  { n: 1, loginId: 'jori_kim', realName: '김지원', status: 'ACTIVE', declared: 'JORI', residence: 'VERIFIED', joined: '2026-08-20', applications: [{ applicationNo: 'A20264-000201', courseName: '초급컴퓨터', displayState: 'CONFIRMED', paymentStatus: 'PAID' }, { applicationNo: 'A20264-000206', courseName: '초급컴퓨터', displayState: 'CANCELLED', paymentStatus: 'PAID' }] },
  { n: 2, loginId: 'jori_lee', realName: '이영희', status: 'ACTIVE', declared: 'JORI', residence: 'UNVERIFIED', joined: '2026-08-21', applications: [{ applicationNo: 'A20264-000202', courseName: '생활영어', displayState: 'CONFIRMED', paymentStatus: 'PAID' }], reviews: [{ reviewId: '1600000000000000000001', kind: 'NAME_CHANGE', state: 'OPEN', reason: '개명에 따른 이름 변경 요청', recordedBy: '김관리', recordedAt: '2026-10-01T10:00:00+09:00', closedNote: null, closedAt: null }] },
  { n: 3, loginId: 'paju_park', realName: '박민수', status: 'ACTIVE', declared: 'OTHER_PAJU', residence: 'UNVERIFIED', joined: '2026-08-25', applications: [{ applicationNo: 'A20264-000203', courseName: '초급컴퓨터', displayState: 'PAYMENT_UNKNOWN', paymentStatus: 'PENDING' }] },
  { n: 4, loginId: 'locked_choi', realName: '최보라', status: 'LOCKED', declared: 'JORI', residence: 'VERIFIED', joined: '2026-08-30', applications: [], reviews: [{ reviewId: '1600000000000000000002', kind: 'RESTRICT', state: 'OPEN', reason: '로그인 실패가 반복되어 이용제한을 검토합니다.', recordedBy: '김관리', recordedAt: '2026-10-05T09:30:00+09:00', closedNote: null, closedAt: null }] },
  { n: 5, loginId: 'out_jung', realName: '정수아', status: 'WITHDRAWN', declared: null, residence: 'UNVERIFIED', joined: '2026-09-02', applications: [] },
  { n: 6, loginId: 'new_hwang', realName: '황도윤', status: 'ACTIVE', declared: null, residence: 'UNVERIFIED', joined: '2026-10-30', applications: [] },
];

const mask = (name: string) => `${name.slice(0, 1)}○○`;

function initialState(): Row[] {
  return SEEDS.map((seed): Row => ({
    realName: seed.realName,
    phone: `010-0000-${String(seed.n).padStart(4, '0')}`,
    email: `member${seed.n}@example.invalid`,
    member: {
      memberId: mid(seed.n),
      loginId: seed.loginId,
      nameMasked: mask(seed.realName),
      residenceDeclared: seed.declared,
      residenceStatus: seed.residence,
      joinedOn: seed.joined,
      status: seed.status,
      phoneMasked: `010-****-${String(seed.n).padStart(4, '0')}`,
      emailMasked: `m***${seed.n}@example.invalid`,
      applicationCount: seed.applications.length,
      paidTotal: seed.applications.filter((app) => app.paymentStatus === 'PAID').length * 60000,
      applications: seed.applications,
      reviews: seed.reviews ?? [],
    },
  }));
}

interface State {
  rows: Row[];
  seq: number;
  /** 연락처 원문 조회 감사기록. 시험이 확인한다. */
  revealLog: Array<{ memberId: string; reason: string; by: string }>;
  idempotent: Map<string, { fingerprint: string; body: Schemas['MemberReview'] }>;
}

let state: State = { rows: initialState(), seq: 10, revealLog: [], idempotent: new Map() };

/** 시험 사이에 회원과 검토 기록을 처음 상태로 되돌린다. */
export function resetMockMembers(): void {
  state = { rows: initialState(), seq: 10, revealLog: [], idempotent: new Map() };
}

export const revealLog = () => state.revealLog;

const find = (id: unknown) => state.rows.find((row) => row.member.memberId === id);
const view = (row: Row): Member => ({ ...row.member, canReview: currentAuthorities().includes('AU.MBR_R') });
const toSummary = (row: Row): Schemas['AdminMemberSummary'] => {
  const m = row.member;
  return { memberId: m.memberId, loginId: m.loginId, nameMasked: m.nameMasked, residenceDeclared: m.residenceDeclared, residenceStatus: m.residenceStatus, joinedOn: m.joinedOn, status: m.status };
};

export const memberHandlers = [
  http.get('/api/admin/v1/members', ({ request }) => {
    const denied = denyUnless('AU.MBR_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const q = params.get('q')?.trim();
    const rows = state.rows.filter((row) => (!q || row.member.loginId.includes(q) || row.realName.includes(q)) && (!params.get('status') || row.member.status === params.get('status')));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size).map(toSummary), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.get('/api/admin/v1/members/:memberId', ({ params }) => {
    const denied = denyUnless('AU.MBR_R');
    if (denied) return denied;
    const row = find(params.memberId);
    return row ? HttpResponse.json(view(row)) : apiError('NOT_FOUND');
  }),

  http.post('/api/admin/v1/members/:memberId/reveal', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.MBR_R');
    if (denied) return denied;
    const row = find(params.memberId);
    if (!row) return apiError('NOT_FOUND');
    const { reason } = (await request.json()) as Schemas['RevealRequest'];
    if (reason.trim().length < 5) return apiError('RULE_REJECTED', { reason: '조회 사유를 5자 이상 입력해 주세요.' });
    state.revealLog.push({ memberId: row.member.memberId, reason: reason.trim(), by: currentAdminName() });
    return HttpResponse.json({ phone: row.phone, email: row.email } satisfies Schemas['MemberContact']);
  }),

  http.post('/api/admin/v1/members/:memberId/reviews', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.MBR_R');
    if (denied) return denied;
    const row = find(params.memberId);
    if (!row) return apiError('NOT_FOUND');
    const body = (await request.json()) as Schemas['MemberReviewCreate'];
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(found.body, { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
    if (row.member.status === 'WITHDRAWN') return apiError('CONFLICT_STATE');
    if (row.member.reviews.some((review) => review.kind === body.kind && review.state === 'OPEN')) {
      return apiError('RULE_REJECTED', { kind: '같은 종류의 검토가 이미 진행 중입니다.' });
    }
    state.seq += 1;
    const created: Schemas['MemberReview'] = { reviewId: `16${String(state.seq).padStart(20, '0')}`, kind: body.kind, state: 'OPEN', reason: body.reason.trim(), recordedBy: currentAdminName(), recordedAt: new Date().toISOString(), closedNote: null, closedAt: null };
    row.member.reviews = [created, ...row.member.reviews];
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: created });
    return HttpResponse.json(created, { status: 201 });
  }),

  http.post('/api/admin/v1/members/:memberId/reviews/:reviewId/close', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.MBR_R');
    if (denied) return denied;
    const row = find(params.memberId);
    const review = row?.member.reviews.find((item) => item.reviewId === params.reviewId);
    if (!row || !review) return apiError('NOT_FOUND');
    if (review.state !== 'OPEN') return apiError('CONFLICT_STATE');
    const { note } = (await request.json()) as Schemas['MemberReviewClose'];
    Object.assign(review, { state: 'CLOSED', closedNote: note.trim(), closedAt: new Date().toISOString() });
    return HttpResponse.json(review);
  }),

  http.post('/api/admin/v1/members/:memberId/residence', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.MBR_R');
    if (denied) return denied;
    const row = find(params.memberId);
    if (!row) return apiError('NOT_FOUND');
    if (row.member.status === 'WITHDRAWN') return apiError('CONFLICT_STATE');
    const { result } = (await request.json()) as Schemas['ResidenceRecord'];
    row.member.residenceStatus = result;
    return HttpResponse.json(view(row));
  }),
];