// 관리자 센터·강의실, 강좌 일정·휴보강을 흉내 내는 모의 서버. 시설 중복·사용 중지·기간 규칙은 서버가 정하는 대로 따른다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, denyCsrf, denyUnless } from './auth';
import { getCourseInfo, registerRoomOptions, setScheduleCount } from './education';

type Facility = Schemas['Facility'];
type FacilityWrite = Schemas['FacilityWrite'];
type Schedule = Schemas['Schedule'];
type ScheduleWrite = Schemas['ScheduleWrite'];
type ScheduleChange = Schemas['ScheduleChange'];
type ScheduleChangeWrite = Schemas['ScheduleChangeWrite'];
type Weekday = Schemas['Weekday'];

const serial = (group: number, n: number) => `${group}${String(n).padStart(21, '0')}`;
const courseId = (n: number) => serial(4, n);

const WEEKDAY_NAME: Record<Weekday, string> = { MON: '월요일', TUE: '화요일', WED: '수요일', THU: '목요일', FRI: '금요일', SAT: '토요일', SUN: '일요일' };
const WEEKDAYS: Weekday[] = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']; // Date.getDay() 순서

interface State {
  facilities: Array<Omit<Facility, 'scheduleCount'>>;
  schedules: Array<Schedule & { courseId: string }>;
  changes: Array<ScheduleChange & { courseId: string }>;
  seq: { facility: number; schedule: number; change: number };
  idempotent: Map<string, { fingerprint: string; body: Facility | Schedule | ScheduleChange }>;
}

function initialState(): State {
  const room = (n: number, name: string, floor: string, inUse = true) => ({
    facilityId: serial(7, n), kind: 'ROOM' as const, parentId: serial(7, 1), name, floor, address: null, isPublic: true, inUse, version: 1,
  });
  const facilities = [
    { facilityId: serial(7, 1), kind: 'CENTER' as const, parentId: null, name: '조리읍 주민자치센터', floor: null, address: '경기도 파주시 조리읍 봉천로 64', isPublic: true, inUse: true, version: 1 },
    room(2, '강의실 1', '3층'),
    room(3, '강의실 2', '3층'),
    room(4, '강의실 3', '2층'),
    room(5, '강의실 4(보수 중)', '2층', false),
  ];
  const room1 = serial(7, 2);
  const room2 = serial(7, 3);
  const room3 = serial(7, 4);
  let seq = 0;
  const row = (course: number, weekday: Weekday, startTime: string, endTime: string, facilityId: string, periodStart = '2026-10-01', periodEnd = '2026-12-31') => {
    seq += 1;
    return {
      scheduleId: serial(8, seq), courseId: courseId(course), weekday, startTime, endTime, facilityId,
      facilityName: `강의실 ${facilityId === room1 ? 1 : facilityId === room2 ? 2 : 3}`, periodStart, periodEnd, version: 1,
    };
  };
  const schedules = [
    row(1, 'TUE', '10:00', '11:30', room1), row(1, 'THU', '10:00', '11:30', room1),
    row(2, 'TUE', '11:30', '13:00', room2), row(2, 'THU', '11:30', '13:00', room2),
    row(3, 'MON', '14:00', '15:30', room3), row(3, 'THU', '14:00', '15:30', room3),
    row(4, 'MON', '19:00', '20:30', room1), row(4, 'TUE', '19:00', '20:30', room1),
    row(5, 'TUE', '13:30', '15:20', room2), row(5, 'THU', '13:30', '15:20', room2),
    row(6, 'TUE', '09:50', '10:50', room3), row(6, 'THU', '09:50', '10:50', room3),
    row(7, 'MON', '20:00', '21:00', room1, '2026-12-01', '2026-12-31'),
    row(8, 'WED', '10:00', '11:00', room1, '2026-12-01', '2026-12-31'), row(8, 'FRI', '10:00', '11:00', room1, '2026-12-01', '2026-12-31'),
  ];
  return { facilities, schedules, changes: [], seq: { facility: 5, schedule: seq, change: 0 }, idempotent: new Map() };
}

let state = initialState();

/** 시험 사이에 시설·일정·휴보강을 처음 상태로 되돌린다. */
export function resetMockCampus(): void {
  state = initialState();
}

const facilityName = (id: string | null) => state.facilities.find((item) => item.facilityId === id)?.name ?? null;
const scheduleCountOf = (id: string) => state.schedules.filter((item) => item.facilityId === id).length;
const withCount = (item: State['facilities'][number]): Facility => ({ ...item, scheduleCount: scheduleCountOf(item.facilityId) });
const syncCount = (id: string) => setScheduleCount(id, state.schedules.filter((item) => item.courseId === id).length);
const unprocessable = (fields: Record<string, string>) => apiError('RULE_REJECTED', fields);

registerRoomOptions(() =>
  state.facilities
    .filter((item) => item.kind === 'ROOM' && item.inUse && state.facilities.find((center) => center.facilityId === item.parentId)?.inUse)
    .map((item) => ({ id: item.facilityId, name: `${facilityName(item.parentId)} ${item.name}` })),
);

const toMinutes = (time: string) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3, 5));
const overlaps = (aStart: string, aEnd: string, bStart: string, bEnd: string) => toMinutes(aStart) < toMinutes(bEnd) && toMinutes(bStart) < toMinutes(aEnd);

/** 같은 시설·요일에 시간이 겹치는 다른 강좌의 일정이 있으면 안내 문구를 돌려준다(FN-049). */
function conflictMessage(facilityId: string, weekday: Weekday, start: string, end: string, from: string, to: string, ownCourse: string, ownSchedule?: string) {
  const other = state.schedules.find(
    (item) =>
      item.facilityId === facilityId && item.weekday === weekday && item.courseId !== ownCourse && item.scheduleId !== ownSchedule &&
      overlaps(start, end, item.startTime, item.endTime) && item.periodStart <= to && from <= item.periodEnd,
  );
  if (!other) return null;
  const name = getCourseInfo(other.courseId)?.name ?? '다른 강좌';
  return `${facilityName(facilityId)} ${WEEKDAY_NAME[weekday]} ${other.startTime}~${other.endTime}에 ${name}이(가) 있습니다.`;
}

function replay(request: Request, body: unknown) {
  const key = request.headers.get('Idempotency-Key');
  const found = key ? state.idempotent.get(key) : undefined;
  if (!found) return null;
  return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(found.body, { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
}
function remember(request: Request, body: unknown, result: Facility | Schedule | ScheduleChange) {
  const key = request.headers.get('Idempotency-Key');
  if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: result });
}

function validateFacility(body: FacilityWrite, ownId?: string): Record<string, string> | null {
  const fields: Record<string, string> = {};
  if (body.kind === 'ROOM') {
    const parent = state.facilities.find((item) => item.facilityId === body.parentId);
    if (!parent || parent.kind !== 'CENTER') fields.parentId = '강의실은 상위 센터를 선택해야 합니다.';
  } else if (body.parentId) fields.parentId = '센터에는 상위 시설이 없습니다.';
  if (state.facilities.some((item) => item.name === body.name && item.parentId === body.parentId && item.facilityId !== ownId)) {
    fields.name = '같은 위치에 같은 이름의 시설이 있습니다.';
  }
  return Object.keys(fields).length > 0 ? fields : null;
}

const READ = ['AU.CORS_R', 'AU.CORS_W'] as const;
const sortSchedules = <T extends Schedule>(items: T[]) => [...items].sort((a, b) => WEEKDAYS.indexOf(a.weekday) - WEEKDAYS.indexOf(b.weekday) || a.startTime.localeCompare(b.startTime));
const findOwn = (cid: string) => getCourseInfo(cid);
/** 강좌 번호는 모의 서버 안에서만 쓰는 값이라 응답에서 뺀다. */
const withoutCourse = <T extends { courseId: string }>(row: T): Omit<T, 'courseId'> => {
  const copy: Partial<T> = { ...row };
  delete copy.courseId;
  return copy as Omit<T, 'courseId'>;
};

export const campusHandlers = [
  http.get('/api/admin/v1/facilities', () => {
    const denied = denyUnless('AU.FCLT_W');
    if (denied) return denied;
    return HttpResponse.json({ items: state.facilities.map(withCount) });
  }),

  http.post('/api/admin/v1/facilities', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.FCLT_W');
    if (denied) return denied;
    const body = (await request.json()) as FacilityWrite;
    const replayed = replay(request, body);
    if (replayed) return replayed;
    const fields = validateFacility(body);
    if (fields) return unprocessable(fields);
    state.seq.facility += 1;
    const created = { ...body, address: body.kind === 'CENTER' ? body.address : null, facilityId: serial(7, state.seq.facility), version: 1 };
    state.facilities.push(created);
    remember(request, body, withCount(created));
    return HttpResponse.json(withCount(created), { status: 201 });
  }),

  http.get('/api/admin/v1/facilities/:facilityId', ({ params }) => {
    const denied = denyUnless('AU.FCLT_W');
    if (denied) return denied;
    const found = state.facilities.find((item) => item.facilityId === params.facilityId);
    return found ? HttpResponse.json(withCount(found)) : apiError('NOT_FOUND');
  }),

  http.put('/api/admin/v1/facilities/:facilityId', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.FCLT_W');
    if (denied) return denied;
    const found = state.facilities.find((item) => item.facilityId === params.facilityId);
    if (!found) return apiError('NOT_FOUND');
    const { version, ...body } = (await request.json()) as Schemas['FacilityUpdate'];
    if (version !== found.version) return apiError('VERSION_CONFLICT');
    const fields = validateFacility(body, found.facilityId);
    if (fields) return unprocessable(fields);
    Object.assign(found, body, { address: body.kind === 'CENTER' ? body.address : null, version: found.version + 1 });
    return HttpResponse.json(withCount(found));
  }),

  http.get('/api/admin/v1/courses/:courseId/schedules', ({ params }) => {
    const denied = denyUnless(...READ);
    if (denied) return denied;
    const cid = String(params.courseId);
    const course = findOwn(cid);
    if (!course) return apiError('NOT_FOUND');
    return HttpResponse.json({
      courseId: cid,
      courseName: course.name,
      schedules: sortSchedules(state.schedules.filter((item) => item.courseId === cid)).map(withoutCourse),
      changes: state.changes.filter((item) => item.courseId === cid).sort((a, b) => a.classDate.localeCompare(b.classDate)).map(withoutCourse),
      canEdit: course.canEdit,
    } satisfies Schemas['CourseSchedules']);
  }),

  http.post('/api/admin/v1/courses/:courseId/schedules', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const cid = String(params.courseId);
    const course = findOwn(cid);
    if (!course) return apiError('NOT_FOUND');
    if (!course.canEdit) return apiError('CONFLICT_STATE');
    const body = (await request.json()) as ScheduleWrite;
    const replayed = replay(request, body);
    if (replayed) return replayed;
    const fields = validateSchedule(body, course);
    if (fields) return unprocessable(fields);
    state.seq.schedule += 1;
    const created: Schedule = { ...body, scheduleId: serial(8, state.seq.schedule), facilityName: facilityName(body.facilityId) ?? '', version: 1 };
    state.schedules.push({ ...created, courseId: cid });
    syncCount(cid);
    remember(request, body, created);
    return HttpResponse.json(created, { status: 201 });
  }),

  http.put('/api/admin/v1/courses/:courseId/schedules/:scheduleId', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const cid = String(params.courseId);
    const course = findOwn(cid);
    const found = state.schedules.find((item) => item.courseId === cid && item.scheduleId === params.scheduleId);
    if (!course || !found) return apiError('NOT_FOUND');
    if (!course.canEdit) return apiError('CONFLICT_STATE');
    const { version, ...body } = (await request.json()) as Schemas['ScheduleUpdate'];
    if (version !== found.version) return apiError('VERSION_CONFLICT');
    const fields = validateSchedule(body, course, found);
    if (fields) return unprocessable(fields);
    Object.assign(found, body, { facilityName: facilityName(body.facilityId) ?? '', version: found.version + 1 });
    return HttpResponse.json(withoutCourse(found));
  }),

  http.delete('/api/admin/v1/courses/:courseId/schedules/:scheduleId', ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const cid = String(params.courseId);
    const course = findOwn(cid);
    const index = state.schedules.findIndex((item) => item.courseId === cid && item.scheduleId === params.scheduleId);
    if (!course || index < 0) return apiError('NOT_FOUND');
    if (!course.canEdit) return apiError('CONFLICT_STATE');
    state.schedules.splice(index, 1);
    syncCount(cid);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post('/api/admin/v1/courses/:courseId/schedule-changes', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const cid = String(params.courseId);
    const course = findOwn(cid);
    if (!course) return apiError('NOT_FOUND');
    if (!course.canEdit) return apiError('CONFLICT_STATE');
    const body = (await request.json()) as ScheduleChangeWrite;
    const replayed = replay(request, body);
    if (replayed) return replayed;
    const fields = validateChange(body, course, cid);
    if (fields) return unprocessable(fields);
    state.seq.change += 1;
    const makeup = body.kind === 'MAKEUP';
    const created: ScheduleChange = {
      ...body,
      facilityId: makeup ? body.facilityId : null,
      startTime: makeup ? body.startTime : null,
      endTime: makeup ? body.endTime : null,
      changeId: serial(9, state.seq.change),
      facilityName: makeup ? facilityName(body.facilityId ?? null) : null,
    };
    state.changes.push({ ...created, courseId: cid });
    remember(request, body, created);
    return HttpResponse.json(created, { status: 201 });
  }),

  http.delete('/api/admin/v1/courses/:courseId/schedule-changes/:changeId', ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const cid = String(params.courseId);
    const course = findOwn(cid);
    const index = state.changes.findIndex((item) => item.courseId === cid && item.changeId === params.changeId);
    if (!course || index < 0) return apiError('NOT_FOUND');
    if (!course.canEdit) return apiError('CONFLICT_STATE');
    state.changes.splice(index, 1);
    return new HttpResponse(null, { status: 204 });
  }),
];

type CourseInfo = NonNullable<ReturnType<typeof getCourseInfo>>;

function validateSchedule(body: ScheduleWrite, course: CourseInfo, own?: Schedule & { courseId: string }): Record<string, string> | null {
  const fields: Record<string, string> = {};
  if (toMinutes(body.endTime) <= toMinutes(body.startTime)) fields.endTime = '종료 시각은 시작 시각 이후여야 합니다.';
  if (body.periodEnd < body.periodStart) fields.periodEnd = '적용 종료일은 시작일 이후여야 합니다.';
  else if (body.periodStart < course.educationStart || body.periodEnd > course.educationEnd) fields.periodStart = '강좌 교육기간 안이어야 합니다.';
  const room = state.facilities.find((item) => item.facilityId === body.facilityId);
  const unchanged = own?.facilityId === body.facilityId;
  if (!room || room.kind !== 'ROOM' || (!room.inUse && !unchanged)) fields.facilityId = '사용 중인 강의실만 선택할 수 있습니다.';
  if (Object.keys(fields).length > 0) return fields;
  const conflict = conflictMessage(body.facilityId, body.weekday, body.startTime, body.endTime, body.periodStart, body.periodEnd, course.courseId, own?.scheduleId);
  return conflict ? { facilityId: conflict } : null;
}

function validateChange(body: ScheduleChangeWrite, course: CourseInfo, cid: string): Record<string, string> | null {
  const fields: Record<string, string> = {};
  if (body.classDate < course.educationStart || body.classDate > course.educationEnd) fields.classDate = '강좌 교육기간 안이어야 합니다.';
  if (body.kind === 'MAKEUP') {
    const room = state.facilities.find((item) => item.facilityId === body.facilityId);
    if (!room || room.kind !== 'ROOM' || !room.inUse) fields.facilityId = '보강은 사용 중인 강의실을 선택해야 합니다.';
    if (!body.startTime) fields.startTime = '보강 시작 시각을 입력해 주세요.';
    if (!body.endTime) fields.endTime = '보강 종료 시각을 입력해 주세요.';
    else if (body.startTime && toMinutes(body.endTime) <= toMinutes(body.startTime)) fields.endTime = '종료 시각은 시작 시각 이후여야 합니다.';
    if (Object.keys(fields).length === 0) {
      const weekday = WEEKDAYS[new Date(`${body.classDate}T00:00:00+09:00`).getDay()]!;
      const conflict = conflictMessage(body.facilityId!, weekday, body.startTime!, body.endTime!, body.classDate, body.classDate, cid);
      if (conflict) fields.facilityId = conflict;
    }
  }
  return Object.keys(fields).length > 0 ? fields : null;
}