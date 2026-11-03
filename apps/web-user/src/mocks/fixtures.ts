// 모의 서버가 돌려주는 데이터. 강좌·기간·연락처는 조리읍 2026년 4분기 공고 값이고 접수·교육 상태는 호출 시각으로 판정한다
import type { Schemas } from '@jori/api-client';
import { CATEGORY_SEEDS, COURSE_SEEDS, type CourseSeed } from './courseData';

type HomeResponse = Schemas['HomeResponse'];
type ContactResponse = Schemas['ContactResponse'];
type ReceptionState = Schemas['ReceptionState'];
type EducationState = Schemas['EducationState'];
type CycleInfo = Schemas['CycleInfo'];
type CourseSummary = Schemas['CourseSummary'];
type CourseDetail = Schemas['CourseDetail'];
type CoursePlan = Schemas['CoursePlan'];
type CoursePage = Schemas['CoursePage'];

// 공고의 접수일(2026.09.07~09.11)에는 시각이 없다. 시험용으로 하루 전체를 접수 시간으로 둔다.
const RECEPTION_START = '2026-09-07T00:00:00+09:00';
const RECEPTION_END = '2026-09-11T23:59:59+09:00';
const EDUCATION_START = '2026-10-01';
const EDUCATION_END = '2026-12-31';
const CYCLE_NAME = '2026년 4분기';

// 시안 상세 페이지의 '강의 안내' 문장이다.
const DESCRIPTION =
  '강좌·강사·일정·정원·수강료는 2026년 4분기 공식 시간표 기준입니다. 세부 강의계획과 준비물 자료는 미수록입니다.';

const kstDate = (now: Date) =>
  new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(now);

/** 서버가 하는 접수 상태 판정을 모의 서버에서 흉내 낸다. 화면은 이 값을 그대로 쓴다. */
export function receptionStateAt(now: Date, start: string, end: string): ReceptionState {
  if (now.getTime() < new Date(start).getTime()) return 'UPCOMING';
  if (now.getTime() <= new Date(end).getTime()) return 'OPEN';
  return 'CLOSED';
}

/** 교육 상태. 날짜만 있는 교육기간을 한국시간 오늘과 비교한다. */
export function educationStateAt(now: Date, startDate: string, endDate: string): EducationState {
  const today = kstDate(now);
  if (today < startDate) return 'UPCOMING';
  if (today <= endDate) return 'ONGOING';
  return 'ENDED';
}

export function buildCycle(now: Date = new Date()): CycleInfo {
  return {
    name: CYCLE_NAME,
    educationStart: EDUCATION_START,
    educationEnd: EDUCATION_END,
    receptionStart: RECEPTION_START,
    receptionEnd: RECEPTION_END,
    receptionState: receptionStateAt(now, RECEPTION_START, RECEPTION_END),
  };
}

const category = (id: string) => CATEGORY_SEEDS.find((item) => item.categoryId === id) ?? null;

// 점유 인원과 대기 정원은 공고에 없는 시험용 값이다. 정원의 60%가 찼다고 본다.
const OCCUPIED_RATIO = 0.6;
const WAIT_CAPACITY = 10;

// 대기신청 흐름을 시연하려고 강좌 하나(라인댄스 A)만 정원이 모두 찬 것으로 둔다.
export const FULL_COURSE_ID = '3';
const FULL_COURSE_WAITING = 2;

export function buildCourseSummary(seed: CourseSeed, now: Date = new Date()): CourseSummary {
  return {
    courseId: seed.id,
    name: seed.name,
    category: category(seed.categoryId),
    instructorName: seed.instructorName,
    schedules: seed.schedules,
    room: seed.room,
    educationStart: EDUCATION_START,
    educationEnd: EDUCATION_END,
    receptionStart: RECEPTION_START,
    receptionEnd: RECEPTION_END,
    receptionState: receptionStateAt(now, RECEPTION_START, RECEPTION_END),
    educationState: educationStateAt(now, EDUCATION_START, EDUCATION_END),
    fee: seed.fee,
    capacity: seed.capacity,
    remainingSeats: seed.id === FULL_COURSE_ID ? 0 : seed.capacity - Math.floor(seed.capacity * OCCUPIED_RATIO),
    waitingCount: seed.id === FULL_COURSE_ID ? FULL_COURSE_WAITING : 0,
  };
}

export function findCourseSeed(id: string): CourseSeed | undefined {
  return COURSE_SEEDS.find((seed) => seed.id === id);
}

export function buildCourseDetail(seed: CourseSeed, now: Date = new Date()): CourseDetail {
  return {
    ...buildCourseSummary(seed, now),
    serverNow: now.toISOString(),
    cycleName: CYCLE_NAME,
    waitCapacity: WAIT_CAPACITY,
    outOfAreaReceptionStart: null,
    description: DESCRIPTION,
    // 강의계획서는 추후 등록한다. 등록 전에는 본문도 파일도 없다.
    hasPlan: false,
  };
}

export function buildCoursePlan(seed: CourseSeed): CoursePlan {
  return { courseId: seed.id, planText: null, planFile: null };
}

export interface CourseQuery {
  q?: string | null;
  categoryId?: string | null;
  day?: string | null;
  status?: string | null;
  page?: number;
  size?: number;
}

/** 목록 조회를 모의 서버에서 흉내 낸다. 검색·분야·요일·접수 상태로 거르고 번호 순으로 쪽을 나눈다. */
export function buildCoursePage(query: CourseQuery, now: Date = new Date()): CoursePage {
  const page = Math.max(1, query.page ?? 1);
  const size = Math.min(50, Math.max(1, query.size ?? 10));
  const needle = query.q?.trim().toLowerCase();

  const matched = COURSE_SEEDS.filter((seed) => {
    if (needle && !`${seed.name} ${seed.instructorName ?? ''}`.toLowerCase().includes(needle)) return false;
    if (query.categoryId && seed.categoryId !== query.categoryId) return false;
    if (query.day && !seed.schedules.some((slot) => (slot.days as string[]).includes(query.day as string)))
      return false;
    if (query.status && receptionStateAt(now, RECEPTION_START, RECEPTION_END) !== query.status) return false;
    return true;
  });

  return {
    items: matched.slice((page - 1) * size, page * size).map((seed) => buildCourseSummary(seed, now)),
    page,
    size,
    total: matched.length,
    criteria: { basisAt: now.toISOString(), description: null, cycle: buildCycle(now) },
  };
}

export function buildCategories(): Schemas['CategoryList'] {
  return { items: CATEGORY_SEEDS };
}

/** 홈의 분야 카드는 강좌 목록과 같은 데이터에서 만든다. 강좌명은 분야 안의 목록 순서 앞 3개다. */
export function buildHome(now: Date = new Date()): HomeResponse {
  const cycle = buildCycle(now);
  return {
    serverNow: now.toISOString(),
    cycle,
    categories: CATEGORY_SEEDS.map((item) => ({
      category: item,
      receptionState: cycle.receptionState,
      receptionStart: RECEPTION_START,
      receptionEnd: RECEPTION_END,
      educationStart: EDUCATION_START,
      educationEnd: EDUCATION_END,
      courseNames: COURSE_SEEDS.filter((seed) => seed.categoryId === item.categoryId)
        .slice(0, 3)
        .map((seed) => seed.name),
    })),
    notices: [
      {
        postId: '101',
        title: '2026년 4분기 조리읍주민자치센터 수강생 모집',
        publishedAt: '2026-09-01T09:00:00+09:00',
        pinned: true,
      },
      {
        postId: '102',
        title: '2026년 통기타 강사 모집 공고',
        publishedAt: '2026-02-19T09:00:00+09:00',
        pinned: true,
      },
    ],
  };
}

export const contact: ContactResponse = {
  phone: '031-941-7742',
  adminOfficePhone: '031-940-8121',
  postalCode: '10937',
  address: '경기도 파주시 조리읍 봉천로 64',
  floorInfo: '조리읍 행정복지센터 3층',
  openHours: null,
  parking: null,
};
