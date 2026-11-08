// 관리자 수강신청 조회와 대기·자리 배정 조회를 흉내 내는 모의 서버. 조회 전용이고 이름은 가려서 주며 신청 원장 이력을 함께 보여 준다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, denyUnless } from './auth';
import { csvResponse } from './csv';
import { courseBriefs } from './education';

type Application = Schemas['AdminApplication'];
type Status = Schemas['ApplicationStatus'];

const courseId = (n: number) => `4${String(n).padStart(21, '0')}`;
const appId = (n: number) => `12${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;
const SURNAMES = ['김', '이', '박', '최', '정', '강', '조', '윤'];

const at = (base: string, addSeconds: number) => new Date(new Date(base).getTime() + addSeconds * 1000).toISOString();

interface Seed {
  course: number;
  name: string;
  status: Status;
  display: Application['displayState'];
  pay: Schemas['PaymentStatus'] | null;
  refund: Schemas['RefundStatus'] | null;
  appliedAt: string;
  waitingOrder?: number;
  replays?: Application['replays'];
}

const SEEDS: Seed[] = [
  { course: 1, name: '김○○', status: 'CONFIRMED', display: 'CONFIRMED', pay: 'PAID', refund: null, appliedAt: '2026-09-07T09:00:03+09:00', replays: [{ at: '2026-09-07T09:00:04+09:00', outcome: 'SAME_RESULT' }] },
  { course: 1, name: '이○○', status: 'HOLD', display: 'PAYMENT_DUE', pay: null, refund: null, appliedAt: '2026-09-07T09:01:10+09:00' },
  { course: 1, name: '박○○', status: 'HOLD', display: 'PAYMENT_UNKNOWN', pay: 'PENDING', refund: null, appliedAt: '2026-09-07T09:02:20+09:00', replays: [{ at: '2026-09-07T09:02:25+09:00', outcome: 'CONFLICT' }] },
  { course: 1, name: '최○○', status: 'WAITING', display: 'WAITING', pay: null, refund: null, appliedAt: '2026-09-07T09:03:30+09:00', waitingOrder: 1 },
  { course: 1, name: '정○○', status: 'WAITING', display: 'WAITING', pay: null, refund: null, appliedAt: '2026-09-07T09:04:40+09:00', waitingOrder: 2 },
  { course: 1, name: '강○○', status: 'CANCELLED', display: 'CANCELLED', pay: 'PAID', refund: 'DONE', appliedAt: '2026-09-07T09:05:00+09:00' },
  { course: 2, name: '조○○', status: 'CONFIRMED', display: 'CONFIRMED', pay: 'PAID', refund: null, appliedAt: '2026-09-07T09:00:30+09:00' },
  { course: 2, name: '윤○○', status: 'EXPIRED', display: 'EXPIRED', pay: null, refund: null, appliedAt: '2026-09-07T09:10:00+09:00' },
  { course: 3, name: '김○○', status: 'WAITING', display: 'WAITING', pay: null, refund: null, appliedAt: '2026-09-08T10:00:00+09:00', waitingOrder: 1 },
  { course: 5, name: '한○○', status: 'CONFIRMED', display: 'CONFIRMED_FREE', pay: null, refund: null, appliedAt: '2026-09-08T11:00:00+09:00' },
  { course: 6, name: '오○○', status: 'CONFIRMED', display: 'CONFIRMED', pay: 'PAID', refund: 'REQUESTED', appliedAt: '2026-09-09T09:30:00+09:00' },
];

function build(): Application[] {
  const briefs = new Map(courseBriefs().map((course) => [course.courseId, course]));
  return SEEDS.map((seed, index): Application => {
    const n = index + 1;
    const brief = briefs.get(courseId(seed.course))!;
    const holds = seed.status !== 'WAITING';
    const history: Application['history'] = [{ at: seed.appliedAt, fromStatus: null, toStatus: holds ? 'HOLD' : 'WAITING', actor: '회원', note: holds ? '신청 접수, 자리 배정' : '신청 접수, 대기 등록' }];
    if (seed.status === 'CONFIRMED' || seed.status === 'CANCELLED') history.push({ at: at(seed.appliedAt, 180), fromStatus: 'HOLD', toStatus: 'CONFIRMED', actor: 'SYSTEM', note: seed.pay ? '결제 승인' : '무료 등록 확정' });
    if (seed.status === 'CANCELLED') history.push({ at: at(seed.appliedAt, 86400), fromStatus: 'CONFIRMED', toStatus: 'CANCELLED', actor: '회원', note: '본인 취소' });
    if (seed.status === 'EXPIRED') history.push({ at: at(seed.appliedAt, 600), fromStatus: 'HOLD', toStatus: 'EXPIRED', actor: 'SYSTEM', note: '결제기한 만료' });
    return {
      applicationId: appId(n),
      applicationNo: `A20264-${String(200 + n).padStart(6, '0')}`,
      courseId: brief.courseId,
      courseName: brief.name,
      cycleName: '2026년 제4기',
      applicantName: seed.name,
      status: seed.status,
      displayState: seed.display,
      paymentStatus: seed.pay,
      refundStatus: seed.refund,
      appliedAt: seed.appliedAt,
      waitingOrder: seed.waitingOrder ?? null,
      seatAllottedAt: holds ? at(seed.appliedAt, 1) : null,
      paymentDeadlineAt: holds ? at(seed.appliedAt, 601) : null,
      history,
      payment: seed.pay ? { orderNo: `ORD-20260907-${String(n).padStart(6, '0')}`, method: 'CARD', amount: seed.course === 5 ? 0 : 60000, status: seed.pay, approvedAt: seed.pay === 'PAID' ? at(seed.appliedAt, 180) : null } : null,
      refund: seed.refund ? { refundNo: `R20264-${String(n).padStart(6, '0')}`, amount: 60000, status: seed.refund } : null,
      replays: seed.replays ?? [],
    };
  });
}

const toSummary = (application: Application): Schemas['AdminApplicationSummary'] => ({
  applicationId: application.applicationId,
  applicationNo: application.applicationNo,
  courseName: application.courseName,
  applicantName: application.applicantName,
  status: application.status,
  displayState: application.displayState,
  paymentStatus: application.paymentStatus,
  refundStatus: application.refundStatus,
  appliedAt: application.appliedAt,
});

const PROMOTIONS: Record<number, Schemas['Promotion'][]> = {
  1: [
    { promotedAt: '2026-09-08T14:02:11+09:00', applicationNo: 'A20264-001001', deadlineAt: '2026-09-08T14:12:11+09:00', smsResult: 'SENT' },
    { promotedAt: '2026-09-09T10:15:40+09:00', applicationNo: 'A20264-001002', deadlineAt: '2026-09-09T10:25:40+09:00', smsResult: 'FAILED' },
  ],
  2: [{ promotedAt: '2026-09-08T09:30:00+09:00', applicationNo: 'A20264-002001', deadlineAt: '2026-09-08T09:40:00+09:00', smsResult: 'SENT' }],
};

const courseNumber = (id: string) => Number(id.slice(1));

function waitlistCourses(): Schemas['WaitlistCourse'][] {
  return courseBriefs().map((course) => {
    const promotions = PROMOTIONS[courseNumber(course.courseId)] ?? [];
    return {
      courseId: course.courseId,
      courseName: course.name,
      capacity: course.capacity,
      occupied: course.occupied,
      waitCount: course.waiting,
      nextWaitOrder: course.waiting > 0 ? 1 : null,
      lastPromotedAt: promotions.length > 0 ? promotions[promotions.length - 1]!.promotedAt : null,
    };
  });
}

function filteredApplications(params: URLSearchParams): Application[] {
  const q = params.get('q')?.trim();
  const from = params.get('from');
  const to = params.get('to');
  return build()
    .filter(
      (row) =>
        (!q || row.applicationNo.includes(q) || row.applicantName.includes(q)) &&
        (!params.get('courseId') || row.courseId === params.get('courseId')) &&
        (!params.get('status') || row.status === params.get('status')) &&
        (!params.get('paymentStatus') || row.paymentStatus === params.get('paymentStatus')) &&
        (!from || row.appliedAt.slice(0, 10) >= from) &&
        (!to || row.appliedAt.slice(0, 10) <= to),
    )
    .sort((a, b) => b.appliedAt.localeCompare(a.appliedAt));
}

// 목록 응답은 가린 이름만 갖고 있어, 명단 내보내기용 실제 이름·연락처는 가린 이름에서 지어낸다. 모두 가짜 값이다.
const GIVEN_NAMES: Record<string, string> = { '김': '지원', '이': '영희', '박': '민수', '최': '보라', '정': '수아', '강': '하늘', '조': '은서', '오': '세훈', '한': '유진' };

export function applicationPiiRows(params: URLSearchParams): string[][] {
  return filteredApplications(params).map((row) => {
    const surname = row.applicantName.slice(0, 1);
    return [row.applicationNo, `${surname}${GIVEN_NAMES[surname] ?? '지우'}`, `010-1111-${row.applicationNo.slice(-4)}`, row.courseName, row.displayState, row.appliedAt];
  });
}

export const applicationHandlers = [
  // 내려받기는 /:applicationId보다 먼저 등록해야 경로가 id로 잡히지 않는다
  http.get('/api/admin/v1/applications/export.csv', ({ request }) => {
    const denied = denyUnless('AU.APLY_R');
    if (denied) return denied;
    const rows = filteredApplications(new URL(request.url).searchParams).map((row) => [
      row.applicationNo, row.courseName, row.applicantName, row.displayState, row.paymentStatus, row.refundStatus, row.appliedAt,
    ]);
    return csvResponse('applications.csv', ['신청번호', '강좌', '신청자', '신청상태', '결제상태', '환불상태', '접수시각'], rows);
  }),

  http.get('/api/admin/v1/applications', ({ request }) => {
    const denied = denyUnless('AU.APLY_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const rows = filteredApplications(params);
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size).map(toSummary), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.get('/api/admin/v1/applications/:applicationId', ({ params }) => {
    const denied = denyUnless('AU.APLY_R');
    if (denied) return denied;
    const found = build().find((row) => row.applicationId === params.applicationId);
    return found ? HttpResponse.json(found) : apiError('NOT_FOUND');
  }),

  http.get('/api/admin/v1/waitlist', ({ request }) => {
    const denied = denyUnless('AU.APLY_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const rows = waitlistCourses();
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.get('/api/admin/v1/waitlist/:courseId', ({ params }) => {
    const denied = denyUnless('AU.APLY_R');
    if (denied) return denied;
    const found = waitlistCourses().find((row) => row.courseId === params.courseId);
    if (!found) return apiError('NOT_FOUND');
    const number = courseNumber(found.courseId);
    const waiters: Schemas['Waiter'][] = Array.from({ length: found.waitCount }, (_, index) => ({
      order: index + 1,
      applicationNo: `A20264-${String(number * 1000 + index + 1).padStart(6, '0')}`,
      applicantName: `${SURNAMES[(index + number) % SURNAMES.length]}○○`,
      appliedAt: `2026-09-07T09:${String(10 + index).padStart(2, '0')}:00+09:00`,
    }));
    return HttpResponse.json({ ...found, waiters, promotions: PROMOTIONS[number] ?? [] } satisfies Schemas['WaitlistDetail']);
  }),
];