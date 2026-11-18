// 연령·성별 집계자료 등록·승인을 흉내 내는 모의 서버. 검토대기로 등록하고 대기 자료만 승인·반려하며 버전은 계열별 다음 번호다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, denyCsrf, denyUnless } from './auth';

type Detail = Schemas['SourceDetail'];
type Create = Schemas['SourceCreate'];

interface State {
  rows: Detail[];
  idempotent: Map<string, { fingerprint: string; id: string }>;
}

const sid = (n: number) => `93${String(n).padStart(20, '0')}`;
const ROWS: Detail['rows'] = [
  { ageGroupId: 'a20', ageGroupName: '20~29세', lowerAge: 20, upperAge: 29, genderId: 'M', genderName: '남', count: 120 },
  { ageGroupId: 'a20', ageGroupName: '20~29세', lowerAge: 20, upperAge: 29, genderId: 'F', genderName: '여', count: 150 },
  { ageGroupId: 'a80', ageGroupName: '80세 이상', lowerAge: 80, upperAge: null, genderId: 'U', genderName: '미상', count: 0 },
];

function initialState(): State {
  const base = { provider: '파주시 주민등록 통계', basisId: '문서-2026-001', dedupeNote: '만 나이, 중복 거주 제외', periodStart: '2026-01-01', periodEnd: '2026-10-31', ageBasisDate: '2026-10-31', registeredAt: '2026-11-01T01:00:00Z' };
  return {
    rows: [
      { ...base, sourceId: sid(1), datasetId: 'age-gender-2026', version: 1, state: 'APPROVED', decidedAt: '2026-11-02T01:00:00Z', decidedBy: '김관리', rows: ROWS },
      { ...base, sourceId: sid(2), datasetId: 'age-gender-2026', version: 2, state: 'WAIT', decidedAt: null, decidedBy: null, rows: ROWS.map((row) => ({ ...row, count: row.count + 1 })), registeredAt: '2026-11-10T01:00:00Z' },
    ],
    idempotent: new Map(),
  };
}

let state = initialState();

/** 시험 사이에 집계자료 목록을 처음 상태로 되돌린다. */
export function resetMockStatsSources(): void {
  state = initialState();
}

const summary = (detail: Detail): Schemas['SourceSummary'] => ({
  sourceId: detail.sourceId, datasetId: detail.datasetId, version: detail.version, provider: detail.provider, periodStart: detail.periodStart, periodEnd: detail.periodEnd,
  ageBasisDate: detail.ageBasisDate, state: detail.state, registeredAt: detail.registeredAt, decidedAt: detail.decidedAt, decidedBy: detail.decidedBy,
});

function invalid(body: Create): Response | null {
  if (body.periodEnd < body.periodStart) return apiError('RULE_REJECTED', { periodEnd: '집계 기간의 끝은 시작보다 빠를 수 없습니다.' });
  const seen = new Set<string>();
  for (const [index, row] of body.rows.entries()) {
    if (row.lowerAge != null && row.upperAge != null && row.lowerAge > row.upperAge) return apiError('RULE_REJECTED', { [`rows[${index}]`]: '하한 연령은 상한 연령보다 클 수 없습니다.' });
    const key = `${row.ageGroupId}|${row.genderId}`;
    if (seen.has(key)) return apiError('RULE_REJECTED', { [`rows[${index}]`]: '같은 연령구간·성별 분류가 두 번 들어 있습니다.' });
    seen.add(key);
  }
  return null;
}

export const statsSourceHandlers = [
  http.get('/api/admin/v1/stats/age-gender/sources', () => {
    const denied = denyUnless('AU.CONF_W', 'AU.GRANT_W');
    if (denied) return denied;
    return HttpResponse.json({ items: [...state.rows].reverse().map(summary) } satisfies Schemas['SourceList']);
  }),

  http.get('/api/admin/v1/stats/age-gender/sources/:sourceId', ({ params }) => {
    const denied = denyUnless('AU.CONF_W', 'AU.GRANT_W');
    if (denied) return denied;
    const found = state.rows.find((row) => row.sourceId === params.sourceId);
    return found ? HttpResponse.json(found) : apiError('NOT_FOUND');
  }),

  http.post('/api/admin/v1/stats/age-gender/sources', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CONF_W');
    if (denied) return denied;
    const body = (await request.json()) as Create;
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(state.rows.find((row) => row.sourceId === found.id), { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
    const bad = invalid(body);
    if (bad) return bad;
    const version = Math.max(0, ...state.rows.filter((row) => row.datasetId === body.datasetId).map((row) => row.version)) + 1;
    const created: Detail = {
      sourceId: sid(state.rows.length + 1), datasetId: body.datasetId, version, provider: body.provider, basisId: body.basisId, dedupeNote: body.dedupeNote,
      periodStart: body.periodStart, periodEnd: body.periodEnd, ageBasisDate: body.ageBasisDate, state: 'WAIT', registeredAt: new Date().toISOString(), decidedAt: null, decidedBy: null,
      rows: body.rows.map((row) => ({ ...row, lowerAge: row.lowerAge ?? null, upperAge: row.upperAge ?? null })),
    };
    state.rows.push(created);
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), id: created.sourceId });
    return HttpResponse.json(created, { status: 201 });
  }),

  ...(['approve', 'reject'] as const).map((action) =>
    http.post(`/api/admin/v1/stats/age-gender/sources/:sourceId/${action}`, ({ request, params }) => {
      const denied = denyCsrf(request) ?? denyUnless('AU.GRANT_W');
      if (denied) return denied;
      const found = state.rows.find((row) => row.sourceId === params.sourceId);
      if (!found) return apiError('NOT_FOUND');
      if (found.state !== 'WAIT') return apiError('CONFLICT_STATE');
      found.state = action === 'approve' ? 'APPROVED' : 'REJECTED';
      found.decidedAt = new Date().toISOString();
      found.decidedBy = currentAdminName();
      return HttpResponse.json(found);
    }),
  ),
];
