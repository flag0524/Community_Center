// 강좌 만족도 집계자료 등록·승인을 흉내 내는 모의 서버. 검토 전으로 등록하고 대기 자료만 승인·반려하며 합계 규칙을 서버처럼 검사한다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, denyCsrf, denyUnless } from './auth';
import { mockCourseIds, mockCourseName } from './education';

type Detail = Schemas['SatisfactionSourceDetail'];
type Create = Schemas['SatisfactionSourceCreate'];

interface State {
  rows: Detail[];
  idempotent: Map<string, { fingerprint: string; id: string }>;
}

const sid = (n: number) => `96${String(n).padStart(20, '0')}`;
const QUESTIONS: Detail['questions'] = [
  { questionId: 'q1', name: '수강 동기', type: 'SINGLE', respondents: 10, minScore: null, maxScore: null, criteria: '단일선택 유효 응답', options: [{ optionId: 'a', name: '취미', count: 7, score: null }, { optionId: 'b', name: '취업', count: 3, score: null }] },
  { questionId: 'q3', name: '강의 만족도', type: 'SCORE', respondents: 10, minScore: '1', maxScore: '5', criteria: '무응답은 점수 없음', options: [{ optionId: '5', name: '매우 만족', count: 6, score: '5' }, { optionId: '3', name: '보통', count: 3, score: '3' }, { optionId: 'x', name: '무응답', count: 1, score: null }] },
];

function initialState(): State {
  const base = { courseId: mockCourseIds()[0] ?? '', courseName: mockCourseName(mockCourseIds()[0] ?? ''), datasetId: 'dgstfn-2026', provider: '센터 만족도 조사', basisId: '조사-2026-03', criteria: '수강생 전수조사', periodStart: '2026-09-01', periodEnd: '2026-10-15', respondents: 12, registeredAt: '2026-11-01T01:00:00Z', questions: QUESTIONS };
  return {
    rows: [
      { ...base, sourceId: sid(1), version: 1, state: 'APPROVED', decidedAt: '2026-11-02T01:00:00Z', decidedBy: '김관리' },
      { ...base, sourceId: sid(2), version: 2, state: 'WAIT', decidedAt: null, decidedBy: null, registeredAt: '2026-11-10T01:00:00Z' },
    ],
    idempotent: new Map(),
  };
}

let state = initialState();

/** 시험 사이에 만족도 자료를 처음 상태로 되돌린다. */
export function resetMockSatisfactionSources(): void {
  state = initialState();
}

const summary = (d: Detail): Schemas['SatisfactionSourceSummary'] => ({
  sourceId: d.sourceId, courseId: d.courseId, courseName: d.courseName, datasetId: d.datasetId, version: d.version, provider: d.provider, periodStart: d.periodStart,
  periodEnd: d.periodEnd, respondents: d.respondents, state: d.state, registeredAt: d.registeredAt, decidedAt: d.decidedAt, decidedBy: d.decidedBy,
});

function invalid(body: Create): Response | null {
  if (body.periodEnd < body.periodStart) return apiError('RULE_REJECTED', { periodEnd: '조사 기간의 끝은 시작보다 빠를 수 없습니다.' });
  if (!mockCourseIds().includes(body.courseId)) return apiError('RULE_REJECTED', { courseId: '이 센터에 없는 강좌입니다.' });
  for (const [index, q] of body.questions.entries()) {
    const field = `questions[${index}]`;
    if (q.respondents > body.respondents) return apiError('RULE_REJECTED', { [field]: '문항 유효응답자 수는 전체 응답자 수보다 클 수 없습니다.' });
    if (q.type === 'SCORE' && (q.minScore == null || q.maxScore == null)) return apiError('RULE_REJECTED', { [field]: '점수 문항은 최소·최대 점수를 모두 입력하고 최소가 최대보다 클 수 없습니다.' });
    const total = q.options.reduce((sum, option) => sum + option.count, 0);
    if (q.type === 'MULTI' ? q.options.some((option) => option.count > q.respondents) : total !== q.respondents) {
      return apiError('RULE_REJECTED', { [field]: q.type === 'MULTI' ? '복수선택의 각 선택 수는 문항 유효응답자 수보다 클 수 없습니다.' : '선택 수의 합이 문항 유효응답자 수와 같아야 합니다.' });
    }
  }
  return null;
}

export const satisfactionSourceHandlers = [
  http.get('/api/admin/v1/stats/satisfaction/sources', () => {
    const denied = denyUnless('AU.CONF_W', 'AU.GRANT_W');
    if (denied) return denied;
    return HttpResponse.json({ items: [...state.rows].reverse().map(summary) } satisfies Schemas['SatisfactionSourceList']);
  }),

  http.get('/api/admin/v1/stats/satisfaction/sources/:sourceId', ({ params }) => {
    const denied = denyUnless('AU.CONF_W', 'AU.GRANT_W');
    if (denied) return denied;
    const found = state.rows.find((row) => row.sourceId === params.sourceId);
    return found ? HttpResponse.json(found) : apiError('NOT_FOUND');
  }),

  http.post('/api/admin/v1/stats/satisfaction/sources', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CONF_W');
    if (denied) return denied;
    const body = (await request.json()) as Create;
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(state.rows.find((row) => row.sourceId === found.id), { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
    const bad = invalid(body);
    if (bad) return bad;
    const version = Math.max(0, ...state.rows.filter((row) => row.courseId === body.courseId && row.datasetId === body.datasetId).map((row) => row.version)) + 1;
    const created: Detail = {
      sourceId: sid(state.rows.length + 1), courseId: body.courseId, courseName: mockCourseName(body.courseId), datasetId: body.datasetId, version,
      provider: body.provider, basisId: body.basisId, criteria: body.criteria, periodStart: body.periodStart, periodEnd: body.periodEnd, respondents: body.respondents,
      state: 'WAIT', registeredAt: new Date().toISOString(), decidedAt: null, decidedBy: null,
      questions: body.questions.map((q) => ({
        questionId: q.questionId, name: q.name, type: q.type, respondents: q.respondents, minScore: q.minScore == null ? null : String(q.minScore), maxScore: q.maxScore == null ? null : String(q.maxScore), criteria: q.criteria,
        options: q.options.map((o) => ({ optionId: o.optionId, name: o.name, count: o.count, score: o.score == null ? null : String(o.score) })),
      })),
    };
    state.rows.push(created);
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), id: created.sourceId });
    return HttpResponse.json(created, { status: 201 });
  }),

  ...(['approve', 'reject'] as const).map((action) =>
    http.post(`/api/admin/v1/stats/satisfaction/sources/:sourceId/${action}`, ({ request, params }) => {
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
