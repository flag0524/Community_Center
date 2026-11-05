// 관리자 출석 현황 조회를 흉내 내는 모의 서버. 조회 전용이고 이름은 가려서 주며 연락처·생년·결제정보는 없다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, denyUnless } from './auth';
import { courseBriefs } from './education';

type Summary = Schemas['AttendanceSummary'];

const serial = (n: number) => `11${String(n).padStart(20, '0')}`;
const SURNAMES = ['김', '이', '박', '최', '정', '강', '조', '윤'];
const PAGE_SIZE = 20;

// [강좌 번호, 수업일, 회차, 출석, 결석, 미체크, 입력상태]
const SEEDS: Array<[number, string, number, number, number, number, Summary['inputStatus']]> = [
  [1, '2026-10-27', 11, 18, 2, 0, 'DONE'],
  [1, '2026-10-29', 12, 15, 1, 4, 'IN_PROGRESS'],
  [2, '2026-10-27', 11, 22, 3, 0, 'DONE'],
  [2, '2026-10-29', 12, 20, 2, 3, 'IN_PROGRESS'],
  [3, '2026-10-26', 9, 17, 3, 0, 'DONE'],
  [4, '2026-10-26', 8, 13, 2, 0, 'DONE'],
  [5, '2026-10-27', 11, 18, 2, 0, 'DONE'],
  [6, '2026-10-29', 12, 25, 3, 0, 'DONE'],
];

const courseId = (n: number) => `4${String(n).padStart(21, '0')}`;

function sheets(): Array<Summary & { number: number }> {
  const briefs = new Map(courseBriefs().map((course) => [course.courseId, course]));
  return SEEDS.map(([course, classDate, session, present, absent, unchecked, inputStatus], index) => {
    const brief = briefs.get(courseId(course))!;
    return {
      number: index + 1, attendanceId: serial(index + 1), courseId: brief.courseId, courseName: brief.name, classDate, session,
      instructorName: brief.instructorName, present, absent, unchecked, inputStatus,
    };
  });
}

const toSummary = (sheet: Summary & { number: number }): Summary => ({
  attendanceId: sheet.attendanceId,
  courseId: sheet.courseId,
  courseName: sheet.courseName,
  classDate: sheet.classDate,
  session: sheet.session,
  instructorName: sheet.instructorName,
  present: sheet.present,
  absent: sheet.absent,
  unchecked: sheet.unchecked,
  inputStatus: sheet.inputStatus,
});

export const attendanceHandlers = [
  http.get('/api/admin/v1/attendance', ({ request }) => {
    const denied = denyUnless('AU.ATND_R');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const cycleOf = new Map(courseBriefs().map((course) => [course.courseId, course.cycleId]));
    const rows = sheets()
      .filter(
        (sheet) =>
          (!params.get('cycleId') || cycleOf.get(sheet.courseId) === params.get('cycleId')) &&
          (!params.get('courseId') || sheet.courseId === params.get('courseId')) &&
          (!params.get('classDate') || sheet.classDate === params.get('classDate')) &&
          (!params.get('inputStatus') || sheet.inputStatus === params.get('inputStatus')),
      )
      .sort((a, b) => b.classDate.localeCompare(a.classDate) || a.courseName.localeCompare(b.courseName));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({
      items: rows.slice((page - 1) * size, page * size).map(toSummary),
      page,
      size,
      total: rows.length,
      criteria: { basisAt: new Date().toISOString(), description: null },
    });
  }),

  http.get('/api/admin/v1/attendance/:attendanceId', ({ params }) => {
    const denied = denyUnless('AU.ATND_R');
    if (denied) return denied;
    const sheet = sheets().find((item) => item.attendanceId === params.attendanceId);
    if (!sheet) return apiError('NOT_FOUND');
    const total = sheet.present + sheet.absent + sheet.unchecked;
    const roster: Schemas['AttendanceRow'][] = Array.from({ length: total }, (_, index) => ({
      name: `${SURNAMES[index % SURNAMES.length]}○○`,
      applicationNo: `A20264-${String(sheet.number * 100 + index + 1).padStart(6, '0')}`,
      memberStatus: '이용중',
      mark: index < sheet.present ? 'PRESENT' : index < sheet.present + sheet.absent ? 'ABSENT' : 'UNCHECKED',
    }));
    return HttpResponse.json({ ...toSummary(sheet), sheetNo: `AT-${String(sheet.number).padStart(4, '0')}`, roster } satisfies Schemas['AttendanceDetail']);
  }),
];