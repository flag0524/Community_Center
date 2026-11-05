// 관리자 교육기수·강좌 관리를 흉내 내는 모의 서버. 상태·권한·정원·버전·멱등 규칙은 서버가 정하는 대로 따른다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAuthorities, denyCsrf, denyUnless } from './auth';

type Cycle = Schemas['Cycle'];
type Course = Schemas['AdminCourse'];
type CourseWrite = Schemas['CourseWrite'];
type CycleWrite = Schemas['CycleWrite'];

const serial = (group: number, n: number) => `${group}${String(n).padStart(21, '0')}`;
const DONG_ID = serial(3, 1);

export const CLASSES = [
  { id: serial(5, 1), name: '컴퓨터' },
  { id: serial(5, 2), name: '어학/교양' },
  { id: serial(5, 3), name: '생활체육/건강' },
  { id: serial(5, 4), name: '문화/취미' },
];
// 승인·활동 강사만 선택지에 나온다(FN-051).
export const INSTRUCTORS = ['추순자', '세이엘리자벧시', '정은경', '안석상', '류성신', '한은경'].map((name, index) => ({
  id: serial(6, index + 1),
  name,
}));

interface IdempotentResult {
  fingerprint: string;
  body: Cycle | Course;
}

interface State {
  cycles: Cycle[];
  courses: Course[];
  cycleSeq: number;
  courseSeq: number;
  idempotent: Map<string, IdempotentResult>;
}

const day = 24 * 3600 * 1000;

function initialState(): State {
  const now = Date.now();
  const base = {
    dongId: DONG_ID,
    receptionStart: '2026-09-07T09:00:00+09:00',
    receptionEnd: '2026-09-11T18:00:00+09:00',
    outsideReceptionStart: null,
    educationStart: '2026-10-01',
    educationEnd: '2026-12-31',
    description: '강의내용, 준비물, 강의계획서를 입력해 주세요.',
  };
  const cycle1 = serial(1, 1);
  const row = (n: number, name: string, classIndex: number, instructorIndex: number, c: number, o: number, w: number, official: number | null, tuition: number): Course => ({
    ...base,
    courseId: serial(4, n),
    cycleId: cycle1,
    classId: CLASSES[classIndex]!.id,
    name,
    instructorId: INSTRUCTORS[instructorIndex]!.id,
    capacity: c,
    waitCapacity: w + 5,
    tuition,
    status: 'PUBLISHED',
    receptionState: 'CLOSED',
    educationState: 'ONGOING',
    officialCapacity: official,
    occupied: o,
    waiting: w,
    scheduleCount: 2,
    version: 1,
    actions: { canEdit: false, canPublish: false, canCloseReception: false, canCancel: false },
  });
  const courses: Course[] = [
    row(1, '초급컴퓨터', 0, 0, 20, 20, 6, 12, 60000),
    row(2, '생활영어', 1, 1, 25, 25, 10, 25, 60000),
    row(3, '라인댄스 A', 2, 2, 20, 20, 15, 25, 60000),
    row(4, '통기타', 3, 3, 15, 15, 4, 15, 60000),
    row(5, '한글문해교실', 1, 4, 24, 20, 3, 20, 0),
    row(6, '요가A(중급)', 2, 5, 30, 28, 11, 20, 60000),
  ];
  // 아래 둘은 시험용이다. 날짜를 지금 기준으로 잡아 접수 상태가 시험 시각과 상관없이 같다.
  courses.push({
    ...row(7, '[시험용] 작성중 강좌', 0, 0, 20, 0, 0, null, 30000),
    status: 'DRAFT',
    receptionState: 'UPCOMING',
    educationState: 'UPCOMING',
    receptionStart: new Date(now + 10 * day).toISOString(),
    receptionEnd: new Date(now + 17 * day).toISOString(),
    educationStart: '2026-12-01',
    educationEnd: '2026-12-31',
    scheduleCount: 1,
  });
  courses.push({
    ...row(8, '[시험용] 접수중 강좌', 2, 2, 20, 12, 0, null, 30000),
    receptionState: 'OPEN',
    educationState: 'UPCOMING',
    receptionStart: new Date(now - 2 * day).toISOString(),
    receptionEnd: new Date(now + 5 * day).toISOString(),
    educationStart: '2026-12-01',
    educationEnd: '2026-12-31',
  });
  return {
    cycles: [
      { cycleId: cycle1, name: '2026년 제4기', year: 2026, order: 4, receptionStart: '2026-09-07', receptionEnd: '2026-09-11', educationStart: '2026-10-01', educationEnd: '2026-12-31', status: 'ACTIVE', version: 1, courseCount: 0 },
      { cycleId: serial(1, 2), name: '2027년 제1기', year: 2027, order: 1, receptionStart: '2026-12-01', receptionEnd: '2026-12-10', educationStart: '2027-01-04', educationEnd: '2027-03-31', status: 'DRAFT', version: 1, courseCount: 0 },
    ],
    courses,
    cycleSeq: 2,
    courseSeq: courses.length,
    idempotent: new Map(),
  };
}

let state = initialState();

/** 시험 사이에 기수·강좌를 처음 상태로 되돌린다. */
export function resetMockEducation(): void {
  state = initialState();
}

/** 출석 모의 서버가 읽는 강좌 요약. */
export const courseBriefs = () =>
  state.courses.map((course) => ({
    courseId: course.courseId,
    name: course.name,
    cycleId: course.cycleId,
    instructorName: instructorName(course.instructorId),
  }));

/** 강의실 선택지는 시설 모의 서버가 정한다. 두 모의 서버가 서로를 불러오지 않도록 등록해서 쓴다. */
let roomOptions: () => Array<{ id: string; name: string }> = () => [];
export const registerRoomOptions = (provider: typeof roomOptions) => {
  roomOptions = provider;
};

/** 일정·휴보강 모의 서버가 읽는 강좌 정보. 일정은 공개·접수마감 상태에서 고칠 수 있고 폐강한 강좌는 고칠 수 없다. */
export function getCourseInfo(courseId: string) {
  const course = state.courses.find((item) => item.courseId === courseId);
  if (!course) return undefined;
  return {
    courseId,
    name: course.name,
    educationStart: course.educationStart,
    educationEnd: course.educationEnd,
    canEdit: currentAuthorities().includes('AU.CORS_W') && course.status !== 'CANCELLED',
  };
}

/** 일정 모의 서버가 강좌의 일정 수를 맞춘다. */
export function setScheduleCount(courseId: string, count: number): void {
  const course = state.courses.find((item) => item.courseId === courseId);
  if (course) course.scheduleCount = count;
}

const EDITABLE: Array<Course['status']> = ['DRAFT', 'PUBLISHED', 'RECEPTION_CLOSED'];

/** 상태와 지금 가진 권한으로 서버가 버튼 가능 여부를 정한다. */
function withActions(course: Course): Course {
  const canWrite = currentAuthorities().includes('AU.CORS_W');
  return {
    ...course,
    actions: {
      canEdit: canWrite && EDITABLE.includes(course.status),
      canPublish: canWrite && course.status === 'DRAFT',
      canCloseReception: canWrite && course.status === 'PUBLISHED' && course.receptionState === 'OPEN',
      canCancel: canWrite && (course.status === 'PUBLISHED' || course.status === 'RECEPTION_CLOSED'),
    },
  };
}

const withCount = (cycle: Cycle): Cycle => ({
  ...cycle,
  courseCount: state.courses.filter((course) => course.cycleId === cycle.cycleId).length,
});

const cycleName = (cycleId: string) => state.cycles.find((cycle) => cycle.cycleId === cycleId)?.name ?? '';
const className = (classId: string) => CLASSES.find((item) => item.id === classId)?.name ?? null;
const instructorName = (id: string) => INSTRUCTORS.find((item) => item.id === id)?.name ?? '';

const unprocessable = (fields: Record<string, string>) => apiError('RULE_REJECTED', fields);
const now = () => new Date().toISOString();

function validateCycle(body: CycleWrite): Record<string, string> | null {
  const fields: Record<string, string> = {};
  if (body.receptionEnd < body.receptionStart) fields.receptionEnd = '모집 종료일은 시작일 이후여야 합니다.';
  if (body.educationEnd < body.educationStart) fields.educationEnd = '교육 종료일은 시작일 이후여야 합니다.';
  return Object.keys(fields).length > 0 ? fields : null;
}

function validateCourse(body: CourseWrite, occupied: number): Record<string, string> | null {
  const fields: Record<string, string> = {};
  const cycle = state.cycles.find((item) => item.cycleId === body.cycleId);
  if (!cycle) fields.cycleId = '기수를 선택해 주세요.';
  if (!INSTRUCTORS.some((item) => item.id === body.instructorId)) fields.instructorId = '승인·활동 강사만 선택할 수 있습니다.';
  if (body.receptionEnd <= body.receptionStart) fields.receptionEnd = '접수 종료는 시작 이후여야 합니다.';
  const outside = body.outsideReceptionStart;
  if (outside && (outside < body.receptionStart || outside >= body.receptionEnd)) {
    fields.outsideReceptionStart = '관외 접수 시작은 접수 시작 이상, 접수 종료 미만이어야 합니다.';
  }
  if (body.educationEnd < body.educationStart) fields.educationEnd = '교육 종료일은 시작일 이후여야 합니다.';
  else if (cycle && (body.educationStart < cycle.educationStart || body.educationEnd > cycle.educationEnd)) {
    fields.educationStart = '기수 교육기간 안이어야 합니다.';
  }
  if (body.capacity < occupied) fields.capacity = `현재 점유 ${occupied}명보다 작게 줄일 수 없습니다.`;
  return Object.keys(fields).length > 0 ? fields : null;
}

/** 같은 멱등키·같은 내용이면 이전 결과를, 내용이 다르면 409를 돌려준다. 처음이면 null이다. */
function replay(request: Request, body: unknown) {
  const key = request.headers.get('Idempotency-Key');
  const found = key ? state.idempotent.get(key) : undefined;
  if (!found) return null;
  return found.fingerprint === JSON.stringify(body)
    ? HttpResponse.json(found.body, { status: 201 })
    : apiError('IDEMPOTENCY_CONFLICT');
}

function remember(request: Request, body: unknown, result: Cycle | Course) {
  const key = request.headers.get('Idempotency-Key');
  if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: result });
}

const READ = ['AU.CORS_R', 'AU.CORS_W'] as const;
const PAGE_SIZE = 20;

function paged<T>(items: T[], page: number, size = PAGE_SIZE) {
  return { items: items.slice((page - 1) * size, page * size), page, size, total: items.length, criteria: { basisAt: now(), description: null } };
}

const findCourse = (id: string) => state.courses.find((course) => course.courseId === id);
const touchCourse = (course: Course, change: Partial<Course>) => Object.assign(course, change, { version: course.version + 1 });

export const educationHandlers = [
  http.get('/api/admin/v1/cycles', ({ request }) => {
    const denied = denyUnless('AU.CONF_W');
    if (denied) return denied;
    const page = Number(new URL(request.url).searchParams.get('page') ?? 1);
    return HttpResponse.json(paged(state.cycles.map(withCount), page));
  }),

  http.post('/api/admin/v1/cycles', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CONF_W');
    if (denied) return denied;
    const body = (await request.json()) as CycleWrite;
    const replayed = replay(request, body);
    if (replayed) return replayed;
    const fields = validateCycle(body);
    if (fields) return unprocessable(fields);
    state.cycleSeq += 1;
    const created = withCount({ ...body, cycleId: serial(1, state.cycleSeq), version: 1, courseCount: 0 });
    state.cycles.push(created);
    remember(request, body, created);
    return HttpResponse.json(created, { status: 201 });
  }),

  http.get('/api/admin/v1/cycles/:cycleId', ({ params }) => {
    const denied = denyUnless('AU.CONF_W');
    if (denied) return denied;
    const cycle = state.cycles.find((item) => item.cycleId === params.cycleId);
    return cycle ? HttpResponse.json(withCount(cycle)) : apiError('NOT_FOUND');
  }),

  http.put('/api/admin/v1/cycles/:cycleId', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CONF_W');
    if (denied) return denied;
    const cycle = state.cycles.find((item) => item.cycleId === params.cycleId);
    if (!cycle) return apiError('NOT_FOUND');
    const { version, ...body } = (await request.json()) as Schemas['CycleUpdate'];
    if (version !== cycle.version) return apiError('VERSION_CONFLICT');
    const fields = validateCycle(body);
    if (fields) return unprocessable(fields);
    Object.assign(cycle, body, { version: cycle.version + 1 });
    return HttpResponse.json(withCount(cycle));
  }),

  http.get('/api/admin/v1/course-options', () => {
    const denied = denyUnless(...READ, 'AU.CONF_W', 'AU.ATND_R');
    if (denied) return denied;
    return HttpResponse.json({
      cycles: state.cycles.map((cycle) => ({ id: cycle.cycleId, name: cycle.name })),
      dongs: [{ id: DONG_ID, name: '조리읍' }],
      classes: CLASSES,
      instructors: INSTRUCTORS,
      courses: state.courses.map((course) => ({ id: course.courseId, name: course.name })),
      rooms: roomOptions(),
    } satisfies Schemas['CourseOptions']);
  }),

  http.get('/api/admin/v1/courses', ({ request }) => {
    const denied = denyUnless(...READ);
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const q = params.get('q')?.trim().toLowerCase();
    const rows = state.courses.filter(
      (course) =>
        (!q || course.name.toLowerCase().includes(q)) &&
        (!params.get('cycleId') || course.cycleId === params.get('cycleId')) &&
        (!params.get('classId') || course.classId === params.get('classId')) &&
        (!params.get('dongId') || course.dongId === params.get('dongId')) &&
        (!params.get('status') || course.status === params.get('status')),
    );
    const summaries: Schemas['AdminCourseSummary'][] = rows.map((course) => ({
      courseId: course.courseId,
      name: course.name,
      cycleName: cycleName(course.cycleId),
      className: className(course.classId),
      instructorName: instructorName(course.instructorId),
      receptionStart: course.receptionStart,
      receptionEnd: course.receptionEnd,
      capacity: course.capacity,
      occupied: course.occupied,
      waiting: course.waiting,
      tuition: course.tuition,
      status: course.status,
      receptionState: course.receptionState,
    }));
    return HttpResponse.json(paged(summaries, Number(params.get('page') ?? 1), Number(params.get('size') ?? PAGE_SIZE)));
  }),

  http.post('/api/admin/v1/courses', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const body = (await request.json()) as CourseWrite;
    const replayed = replay(request, body);
    if (replayed) return replayed;
    const fields = validateCourse(body, 0);
    if (fields) return unprocessable(fields);
    state.courseSeq += 1;
    const created: Course = {
      ...body,
      courseId: serial(4, state.courseSeq),
      status: 'DRAFT',
      receptionState: 'UPCOMING',
      educationState: 'UPCOMING',
      officialCapacity: null,
      occupied: 0,
      waiting: 0,
      scheduleCount: 0,
      version: 1,
      actions: { canEdit: true, canPublish: true, canCloseReception: false, canCancel: false },
    };
    state.courses.push(created);
    remember(request, body, withActions(created));
    return HttpResponse.json(withActions(created), { status: 201 });
  }),

  http.get('/api/admin/v1/courses/:courseId', ({ params }) => {
    const denied = denyUnless(...READ);
    if (denied) return denied;
    const course = findCourse(String(params.courseId));
    return course ? HttpResponse.json(withActions(course)) : apiError('NOT_FOUND');
  }),

  http.put('/api/admin/v1/courses/:courseId', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const course = findCourse(String(params.courseId));
    if (!course) return apiError('NOT_FOUND');
    const { version, ...body } = (await request.json()) as Schemas['CourseUpdate'];
    if (!withActions(course).actions.canEdit) return apiError('CONFLICT_STATE');
    if (version !== course.version) return apiError('VERSION_CONFLICT');
    const fields = validateCourse(body, course.occupied);
    if (fields) return unprocessable(fields);
    touchCourse(course, body);
    return HttpResponse.json(withActions(course));
  }),

  http.post('/api/admin/v1/courses/:courseId/publish', ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const course = findCourse(String(params.courseId));
    if (!course) return apiError('NOT_FOUND');
    if (course.status !== 'DRAFT') return apiError('CONFLICT_STATE');
    // 공개 요청 검사: 승인 강사, 일정 1건 이상, 기수 내 기간, 접수기간.
    if (course.scheduleCount < 1) return unprocessable({ schedule: '일정이 1건 이상 있어야 공개할 수 있습니다.' });
    touchCourse(course, { status: 'PUBLISHED' });
    return HttpResponse.json(withActions(course));
  }),

  http.post('/api/admin/v1/courses/:courseId/close-reception', ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const course = findCourse(String(params.courseId));
    if (!course) return apiError('NOT_FOUND');
    if (!withActions(course).actions.canCloseReception) return apiError('CONFLICT_STATE');
    touchCourse(course, { status: 'RECEPTION_CLOSED', receptionState: 'CLOSED' });
    return HttpResponse.json(withActions(course));
  }),

  http.get('/api/admin/v1/courses/:courseId/cancel-preview', ({ params }) => {
    const denied = denyUnless(...READ);
    if (denied) return denied;
    const course = findCourse(String(params.courseId));
    return course
      ? HttpResponse.json({ applicationCount: course.occupied + course.waiting, paidCount: course.occupied } satisfies Schemas['CancelPreview'])
      : apiError('NOT_FOUND');
  }),

  http.post('/api/admin/v1/courses/:courseId/cancel-course', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const course = findCourse(String(params.courseId));
    if (!course) return apiError('NOT_FOUND');
    const { reason } = (await request.json()) as Schemas['CancelCourseRequest'];
    if (!reason.trim()) return unprocessable({ reason: '폐강 사유를 입력해 주세요.' });
    if (!withActions(course).actions.canCancel) return apiError('CONFLICT_STATE');
    touchCourse(course, { status: 'CANCELLED' });
    return HttpResponse.json(withActions(course));
  }),
];