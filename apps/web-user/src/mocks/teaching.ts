// 강사의 담당 강좌와 출석 입력을 흉내 내는 모의 서버. 시험 강사 계정에만 담당 강좌가 있고 저장 직전에 명단과 버전을 확인한다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { DEMO_INSTRUCTOR, apiError, csrfRejected, currentMockMember } from './auth';

type Mark = Schemas['AttendanceMark'];
type Session = Schemas['TeachingSession'];
type Sheet = Schemas['TeachingSheet'];

export const MOCK_ROSTER_CHANGED = '명단이 변경되었습니다. 다시 불러온 뒤 저장하세요.';
const COURSE = { courseId: '3000000000000000000001', courseName: '건강요가 초급' };
const SCHEDULE_ID = '4000000000000000000001';
const LESSONS = [
  { classDate: '2026-11-09', scheduleId: SCHEDULE_ID, changeId: null, session: 1, startTime: '10:00', endTime: '12:00', makeup: false },
  { classDate: '2026-11-04', scheduleId: SCHEDULE_ID, changeId: '4100000000000000000001', session: 1, startTime: '14:00', endTime: '16:00', makeup: true },
];

interface Saved {
  attendanceId: string;
  version: number;
  marks: Map<string, Mark>;
}
interface State {
  students: Array<{ applicationId: string; name: string }>;
  sheets: Map<string, Saved>; // 수업일별
  seq: number;
}

const initialState = (): State => ({
  students: [
    { applicationId: '2000000000000000000011', name: '김*수' },
    { applicationId: '2000000000000000000012', name: '이*희' },
    { applicationId: '2000000000000000000013', name: '홍*동' },
  ],
  sheets: new Map(),
  seq: 0,
});

let state = initialState();

export function resetMockTeaching(): void {
  state = initialState();
}

/** 시험에서 입력하는 사이에 수강생이 늘어난 것처럼 만든다. */
export function addMockStudent(applicationId: string, name: string): void {
  state.students.push({ applicationId, name });
}

const isInstructor = () => currentMockMember()?.loginId === DEMO_INSTRUCTOR.loginId;

function sessionOf(lesson: (typeof LESSONS)[number]): Session {
  const saved = state.sheets.get(lesson.classDate);
  const done = saved && state.students.every((s) => (saved.marks.get(s.applicationId) ?? 'UNCHECKED') !== 'UNCHECKED');
  return { ...lesson, status: !saved ? 'NOT_STARTED' : done ? 'DONE' : 'IN_PROGRESS', attendanceId: saved?.attendanceId ?? null };
}

function sheetOf(lesson: (typeof LESSONS)[number]): Sheet {
  const saved = state.sheets.get(lesson.classDate);
  const roster = state.students.map((s) => ({ ...s, mark: saved?.marks.get(s.applicationId) ?? ('UNCHECKED' as Mark) }));
  const count = (mark: Mark) => roster.filter((entry) => entry.mark === mark).length;
  return {
    ...sessionOf(lesson),
    ...COURSE,
    version: saved?.version ?? null,
    roster,
    present: count('PRESENT'),
    absent: count('ABSENT'),
    unchecked: count('UNCHECKED'),
  };
}

type Write = { confirmed: boolean; marks: Array<{ applicationId: string; mark: Mark }> };

function rejected(body: Write) {
  if (!body.confirmed) return apiError('RULE_REJECTED', { confirmed: '입력 내용을 확인해 주세요.' });
  const sent = new Set(body.marks.map((m) => m.applicationId));
  if (sent.size !== state.students.length || !state.students.every((s) => sent.has(s.applicationId))) {
    return HttpResponse.json({ code: 'CONFLICT_STATE', message: MOCK_ROSTER_CHANGED, fields: null, requestId: 'mock-roster-0001' }, { status: 409 });
  }
  return null;
}

export const teachingHandlers = [
  http.get('/api/v1/me/teaching/courses', () => {
    if (!currentMockMember()) return apiError('UNAUTHENTICATED');
    const items = isInstructor() ? [{ ...COURSE, sessions: LESSONS.map(sessionOf) }] : [];
    return HttpResponse.json({ items } satisfies Schemas['TeachingCourseList']);
  }),

  http.get('/api/v1/me/teaching/attendance', ({ request }) => {
    if (!currentMockMember()) return apiError('UNAUTHENTICATED');
    const query = new URL(request.url).searchParams;
    const lesson = LESSONS.find((item) => item.classDate === query.get('classDate'));
    if (!isInstructor() || query.get('courseId') !== COURSE.courseId || !lesson) return apiError('NOT_FOUND');
    return HttpResponse.json(sheetOf(lesson));
  }),

  http.post('/api/v1/me/teaching/attendance', async ({ request }) => {
    if (!currentMockMember()) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const body = (await request.json()) as Schemas['TeachingAttendanceCreate'];
    const lesson = LESSONS.find((item) => item.classDate === body.classDate);
    if (!isInstructor() || !lesson) return apiError('NOT_FOUND');
    if (state.sheets.has(lesson.classDate)) return apiError('CONFLICT_STATE');
    const failure = rejected(body);
    if (failure) return failure;
    state.seq += 1;
    state.sheets.set(lesson.classDate, {
      attendanceId: `50000000000000000000${String(state.seq).padStart(2, '0')}`,
      version: 1,
      marks: new Map(body.marks.map((m) => [m.applicationId, m.mark])),
    });
    return HttpResponse.json(sheetOf(lesson), { status: 201 });
  }),

  http.put('/api/v1/me/teaching/attendance/:attendanceId', async ({ request, params }) => {
    if (!currentMockMember()) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const body = (await request.json()) as Schemas['TeachingAttendanceUpdate'];
    const found = [...state.sheets].find(([, saved]) => saved.attendanceId === params.attendanceId);
    if (!isInstructor() || !found) return apiError('NOT_FOUND');
    const [classDate, saved] = found;
    if (saved.version !== body.version) return apiError('VERSION_CONFLICT');
    const failure = rejected(body);
    if (failure) return failure;
    saved.version += 1;
    saved.marks = new Map(body.marks.map((m) => [m.applicationId, m.mark]));
    return HttpResponse.json(sheetOf(LESSONS.find((item) => item.classDate === classDate)!));
  }),
];
