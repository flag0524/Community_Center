// 관리자 대시보드·통계를 흉내 내는 모의 서버. 고정 표본을 집계한 값이며 기수가 다르면 자료 없음을 돌려준다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { currentAuthorities, denyUnless } from './auth';
import { csvResponse } from './csv';

const CYCLE_WITH_DATA = '1000000000000000000001';
const cid = (n: number) => `4${String(n).padStart(21, '0')}`;

const DEMAND: Schemas['DemandRow'][] = [
  { courseId: cid(1), courseName: '건강요가 초급', categoryName: '생활체육/건강', capacity: 20, applications: 31, uniqueApplicants: 28, confirmed: 14, hold: 3, paymentUnknown: 1, waiting: 7, cancelled: 6, seatsHeld: 18, effectiveDemand: 25, demandRatio: 1.25 },
  { courseId: cid(2), courseName: '스마트폰 기초', categoryName: '컴퓨터', capacity: 20, applications: 22, uniqueApplicants: 21, confirmed: 15, hold: 2, paymentUnknown: 0, waiting: 1, cancelled: 4, seatsHeld: 17, effectiveDemand: 18, demandRatio: 0.9 },
  { courseId: cid(3), courseName: '서예교실', categoryName: '문화/취미', capacity: 15, applications: 9, uniqueApplicants: 9, confirmed: 8, hold: 0, paymentUnknown: 0, waiting: 0, cancelled: 1, seatsHeld: 8, effectiveDemand: 8, demandRatio: 0.53 },
];
const SETTLEMENT: Omit<Schemas['SettlementStats'], 'basis'> = {
  approvedAmount: 7_640_000, refundedAmount: 400_000, netRevenue: 7_240_000, unknownAmount: 120_000,
  byMethod: [
    { method: 'CARD', approved: 5_000_000, refunded: 300_000, net: 4_700_000 },
    { method: 'TRANSFER', approved: 2_640_000, refunded: 100_000, net: 2_540_000 },
  ],
};
const ATTENDANCE: Schemas['AttendanceStatsRow'][] = [
  { courseId: cid(1), courseName: '건강요가 초급', instructorName: '김강사', present: 90, absent: 10, rate: 90 },
  { courseId: cid(2), courseName: '스마트폰 기초', instructorName: '이강사', present: 71, absent: 29, rate: 71 },
  { courseId: cid(3), courseName: '서예교실', instructorName: '박강사', present: 0, absent: 0, rate: null },
];
const SOURCE: Schemas['StatsSource'] = { version: '2026-상반기 v2', provider: '파주시 행정복지센터', period: '2026-01-01 ~ 2026-06-30', basisDate: '2026-06-30' };
const AGE_GENDER: Schemas['AgeGenderRow'][] = [
  { band: '20~39세', male: 12, female: 48, unknown: 0 },
  { band: '40~59세', male: 35, female: 120, unknown: 2 },
  { band: '60세 이상', male: 80, female: 210, unknown: 0 },
];
const SATISFACTION: Schemas['SatisfactionItem'][] = [
  { question: '강의 내용에 만족하셨습니까', answered: 180, average: 4.4, options: [{ label: '매우 만족', count: 110 }, { label: '만족', count: 55 }, { label: '보통', count: 15 }, { label: '불만족', count: 0 }] },
  { question: '시설 이용이 편리했습니까', answered: 0, average: null, options: [] },
];
const TASKS: Array<{ kind: Schemas['DashboardTaskKind']; count: number; need: Schemas['AdminAuthority'] }> = [
  { kind: 'PAYMENT_UNKNOWN', count: 1, need: 'AU.STLM_R' },
  { kind: 'REFUND_REVIEW', count: 2, need: 'AU.RFND_A' },
  { kind: 'INSTRUCTOR_REVIEW', count: 1, need: 'AU.CORS_R' },
  { kind: 'INQUIRY_ANSWER', count: 3, need: 'AU.POST_W' },
  { kind: 'SMS_FAILED', count: 4, need: 'AU.SMS_SEND' },
];

const basis = (params: URLSearchParams): Schemas['StatsBasis'] => ({ basisAt: new Date().toISOString(), cycleId: params.get('cycleId'), fromDate: params.get('from'), toDate: params.get('to') });
const hasData = (params: URLSearchParams) => !params.get('cycleId') || params.get('cycleId') === CYCLE_WITH_DATA;

function demandRows(params: URLSearchParams): Schemas['DemandRow'][] {
  const category = params.get('categoryId');
  return hasData(params) ? DEMAND.filter((row) => !category || (category === '5000000000000000000003' ? row.categoryName === '생활체육/건강' : row.categoryName === '컴퓨터')) : [];
}

const metaOf = (title: string, params: URLSearchParams): string[] => [
  title,
  `조건 기수 ${params.get('cycleId') ?? '전체'} · 기간 ${params.get('from') ?? '처음'} ~ ${params.get('to') ?? '오늘'}`,
  `집계 기준 ${new Date().toISOString()}`,
];

export const statsHandlers = [
  http.get('/api/admin/v1/dashboard', ({ request }) => {
    const denied = denyUnless('AU.STAT_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const data = hasData(params);
    const mine = currentAuthorities();
    return HttpResponse.json({
      basis: basis(params),
      summary: data ? { applications: 62, uniqueApplicants: 55, confirmed: 37, seatsHeld: 43, waiting: 8, cancelled: 11, netRevenue: SETTLEMENT.netRevenue } : null,
      tasks: TASKS.filter((task) => mine.includes(task.need)).map(({ kind, count }) => ({ kind, count })),
      demand: data ? DEMAND.map((row) => ({ courseId: row.courseId, courseName: row.courseName, effectiveDemand: row.effectiveDemand, capacity: row.capacity })) : [],
      recent: data ? [{ at: '2026-10-30T14:18:00+09:00', actor: 'SYSTEM', action: '대기 승격', target: '건강요가 초급' }, { at: '2026-10-30T14:10:00+09:00', actor: '박정산', action: '환불 승인', target: 'R20264-000012' }] : [],
    } satisfies Schemas['Dashboard']);
  }),

  // 통계 내려받기는 첫 줄들에 집계 조건과 만든 시각을 주석 행으로 넣는다
  http.get('/api/admin/v1/stats/demand/export.csv', ({ request }) => {
    const denied = denyUnless('AU.STAT_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const rows = demandRows(params).map((r) => [r.courseName, r.categoryName, r.capacity, r.applications, r.uniqueApplicants, r.confirmed, r.hold, r.paymentUnknown, r.waiting, r.cancelled, r.seatsHeld, r.effectiveDemand, r.demandRatio]);
    return csvResponse('demand-stats.csv', ['강좌', '분야', '정원', '신청건', '고유 신청자', '등록완료', '결제대기', '승인확인중', '대기', '취소', '좌석점유', '유효수요', '유효수요/정원'], rows, metaOf('수요 통계', params));
  }),

  http.get('/api/admin/v1/stats/settlement/export.csv', ({ request }) => {
    const denied = denyUnless('AU.STAT_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const data = hasData(params) ? SETTLEMENT : { ...SETTLEMENT, byMethod: [], unknownAmount: 0 };
    const rows: (string | number | null)[][] = data.byMethod.map((r) => [r.method, r.approved, r.refunded, r.net, null]);
    // 확인 중 금액은 순수납에 넣지 않고 따로 한 줄로 둔다
    if (data.byMethod.length > 0) rows.push(['확인 중(순수납 제외)', null, null, null, data.unknownAmount]);
    return csvResponse('settlement-stats.csv', ['결제수단', '승인금액', '완료환불액', '순수납', '확인 중 금액'], rows, metaOf('정산 통계', params));
  }),

  http.get('/api/admin/v1/stats/age-gender/export.csv', () => {
    const denied = denyUnless('AU.STAT_R');
    if (denied) return denied;
    const meta = ['연령·성별 통계', `자료 버전 ${SOURCE.version}`, `제공 기관 ${SOURCE.provider}`, `기간 ${SOURCE.period}`, `기준일 ${SOURCE.basisDate}`];
    return csvResponse('age-gender-stats.csv', ['연령 구간', '남', '여', '미상'], AGE_GENDER.map((r) => [r.band, r.male, r.female, r.unknown]), meta);
  }),

  http.get('/api/admin/v1/stats/demand', ({ request }) => {
    const denied = denyUnless('AU.STAT_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const rows = demandRows(params);
    return HttpResponse.json({ basis: basis(params), rows } satisfies Schemas['DemandStats']);
  }),

  http.get('/api/admin/v1/stats/settlement', ({ request }) => {
    const denied = denyUnless('AU.STAT_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const zero = { approvedAmount: 0, refundedAmount: 0, netRevenue: 0, unknownAmount: 0, byMethod: [] };
    return HttpResponse.json({ basis: basis(params), ...(hasData(params) ? SETTLEMENT : zero) } satisfies Schemas['SettlementStats']);
  }),

  http.get('/api/admin/v1/stats/attendance', ({ request }) => {
    const denied = denyUnless('AU.STAT_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    return HttpResponse.json({ basis: basis(params), rows: hasData(params) ? ATTENDANCE : [] } satisfies Schemas['AttendanceStatsReport']);
  }),

  http.get('/api/admin/v1/stats/age-gender', () => {
    const denied = denyUnless('AU.STAT_R');
    if (denied) return denied;
    return HttpResponse.json({ basis: basis(new URLSearchParams()), source: SOURCE, rows: AGE_GENDER } satisfies Schemas['AgeGenderStats']);
  }),

  http.get('/api/admin/v1/stats/satisfaction', () => {
    const denied = denyUnless('AU.STAT_R');
    if (denied) return denied;
    return HttpResponse.json({ basis: basis(new URLSearchParams()), source: SOURCE, respondents: 180, items: SATISFACTION } satisfies Schemas['SatisfactionStats']);
  }),
];