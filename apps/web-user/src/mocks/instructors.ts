// 공개 강사, 모집공고, 강사 지원을 흉내 내는 모의 서버. 강사는 시간표의 담당 강사에서 만들고 모집·지원 상태는 서버가 정한다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, csrfRejected, currentMockMember } from './auth';
import { mockNow } from './clock';
import { CATEGORY_SEEDS, COURSE_SEEDS } from './courseData';

type Status = Schemas['RecruitmentStatus'];
type Application = Schemas['InstructorApplication'];

const categoryName = (id: string) => CATEGORY_SEEDS.find((item) => item.categoryId === id)?.name ?? null;

// 시간표에 처음 나오는 순서대로 번호를 준다(시안의 강사 번호와 같다).
const INSTRUCTORS = (() => {
  const map = new Map<string, { name: string; categoryId: string; courses: string[] }>();
  for (const seed of COURSE_SEEDS) {
    if (!seed.instructorName) continue;
    const entry = map.get(seed.instructorName) ?? { name: seed.instructorName, categoryId: seed.categoryId, courses: [] };
    entry.courses.push(seed.name);
    map.set(seed.instructorName, entry);
  }
  return [...map.values()].map((entry, index) => ({ ...entry, instructorId: String(index + 1) }));
})();

const GUIDE = '자격·제출서류·심사 세부사항은 공고 원본을 확인해야 합니다.';
// 공고는 통기타 한 건이 실제 자료다. 모집중 상태를 시연하려고 시험용 공고 하나를 더 둔다.
const RECRUITMENTS = [
  {
    recruitmentId: '1',
    title: '2026년 조리읍 주민자치센터 통기타 강사 모집',
    announcedOn: '2026-02-19',
    periodStart: '2026-02-23',
    periodEnd: '2026-03-13',
    headcount: 1,
    field: '통기타',
    guide: GUIDE,
  },
  {
    recruitmentId: '2',
    title: '[시험용] 2026년 조리읍 주민자치센터 요가 강사 모집',
    announcedOn: '2026-08-25',
    periodStart: '2026-09-01',
    periodEnd: '2026-09-30',
    headcount: 2,
    field: '요가',
    guide: GUIDE,
  },
];

const kstDate = (now: Date) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(now);
const statusOf = (item: (typeof RECRUITMENTS)[number], now: Date): Status => {
  const today = kstDate(now);
  if (today < item.periodStart) return 'UPCOMING';
  return today <= item.periodEnd ? 'OPEN' : 'CLOSED';
};

interface Stored {
  memberId: string;
  application: Application;
}
interface State {
  items: Map<string, Stored>;
  keys: Map<string, string>;
  seq: number;
}
const initialState = (): State => ({ items: new Map(), keys: new Map(), seq: 0 });
let state = initialState();

/** 시험 사이에 강사 지원 내역을 비운다. */
export function resetMockInstructors(): void {
  state = initialState();
}

const paging = (url: string) => {
  const search = new URL(url).searchParams;
  return {
    q: search.get('q')?.trim().toLowerCase(),
    page: Math.max(1, Number(search.get('page')) || 1),
    size: Math.min(50, Math.max(1, Number(search.get('size')) || 10)),
  };
};
const pageOf = <T>(items: T[], page: number, size: number) => ({
  items: items.slice((page - 1) * size, page * size),
  page,
  size,
  total: items.length,
  criteria: { basisAt: new Date().toISOString(), description: null },
});

const instructorSummary = (entry: (typeof INSTRUCTORS)[number]) => ({
  instructorId: entry.instructorId,
  name: entry.name,
  categoryName: categoryName(entry.categoryId),
  courseNames: entry.courses,
});

const rule = (message: string) =>
  HttpResponse.json({ code: 'RULE_REJECTED', message, fields: null, requestId: 'mock-rule_rejected-0001' }, { status: 422 });

const applied = (memberId: string, recruitmentId: string) =>
  [...state.items.values()].some((item) => item.memberId === memberId && item.application.recruitmentId === recruitmentId);

function validate(body: Schemas['InstructorApplyWrite']) {
  const fields: Record<string, string> = {};
  if (!body.desiredCourse?.trim()) fields.desiredCourse = '희망 강좌명을 입력해 주세요.';
  if (!body.career?.trim()) fields.career = '경력 및 강의소개를 입력해 주세요.';
  if (!categoryName(body.categoryId)) fields.categoryId = '희망 분야를 확인해 주세요.';
  return fields;
}

export const instructorHandlers = [
  http.get('/api/v1/instructors', ({ request }) => {
    const { q, page, size } = paging(request.url);
    const matched = INSTRUCTORS.filter(
      (entry) => !q || entry.name.toLowerCase().includes(q) || entry.courses.some((course) => course.toLowerCase().includes(q)),
    );
    return HttpResponse.json(pageOf(matched.map(instructorSummary), page, size));
  }),

  http.get('/api/v1/instructors/:instructorId', ({ params }) => {
    const entry = INSTRUCTORS.find((item) => item.instructorId === String(params.instructorId));
    // 경력·자격은 공식 시간표에 없어 null이다.
    return entry ? HttpResponse.json({ ...instructorSummary(entry), career: null }) : apiError('NOT_FOUND');
  }),

  http.get('/api/v1/instructor-recruitments', ({ request }) => {
    const { page, size } = paging(request.url);
    const now = mockNow();
    const sorted = [...RECRUITMENTS].sort((a, b) => b.announcedOn.localeCompare(a.announcedOn));
    return HttpResponse.json(
      pageOf(
        sorted.map((item) => ({
          recruitmentId: item.recruitmentId,
          title: item.title,
          status: statusOf(item, now),
          periodStart: item.periodStart,
          periodEnd: item.periodEnd,
          headcount: item.headcount,
        })),
        page,
        size,
      ),
    );
  }),

  http.get('/api/v1/instructor-recruitments/:recruitmentId', ({ params }) => {
    const item = RECRUITMENTS.find((entry) => entry.recruitmentId === String(params.recruitmentId));
    if (!item) return apiError('NOT_FOUND');
    const status = statusOf(item, mockNow());
    const memberId = currentMockMember()?.memberId;
    return HttpResponse.json({
      ...item,
      status,
      canApply: status === 'OPEN' && !(memberId && applied(memberId, item.recruitmentId)),
    });
  }),

  http.get('/api/v1/me/instructor-applications', ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const { page, size } = paging(request.url);
    const mine = [...state.items.values()].filter((item) => item.memberId === member.memberId).map((item) => item.application).reverse();
    return HttpResponse.json(pageOf(mine, page, size));
  }),

  http.get('/api/v1/me/instructor-applications/:applicationId', ({ params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    const found = state.items.get(String(params.applicationId));
    return found && found.memberId === member.memberId ? HttpResponse.json(found.application) : apiError('NOT_FOUND');
  }),

  http.post('/api/v1/me/instructor-applications', async ({ request }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const key = request.headers.get('Idempotency-Key');
    if (!key) return apiError('VALIDATION_FAILED', { 'Idempotency-Key': '멱등키가 필요합니다.' });
    const known = state.keys.get(key);
    if (known) return HttpResponse.json(state.items.get(known)!.application, { status: 201 });
    const body = (await request.json()) as Schemas['InstructorApplyWrite'];
    const fields = validate(body);
    if (Object.keys(fields).length > 0) return apiError('VALIDATION_FAILED', fields);
    const recruitment = RECRUITMENTS.find((item) => item.recruitmentId === body.recruitmentId);
    if (!recruitment) return apiError('NOT_FOUND');
    // 직접 요청도 같은 검사를 한다.
    if (statusOf(recruitment, mockNow()) !== 'OPEN') return rule('모집중인 공고만 지원할 수 있습니다.');
    if (applied(member.memberId, recruitment.recruitmentId)) return rule('이미 지원한 공고입니다.');
    state.seq += 1;
    const application: Application = {
      applicationId: String(5_000_000_000_000_000_000_000n + BigInt(state.seq)),
      recruitmentId: recruitment.recruitmentId,
      recruitmentTitle: recruitment.title,
      desiredCourse: body.desiredCourse.trim(),
      categoryId: body.categoryId,
      categoryName: categoryName(body.categoryId)!,
      career: body.career.trim(),
      status: 'REVIEWING',
      appliedAt: mockNow().toISOString(),
      canEdit: true,
    };
    state.items.set(application.applicationId, { memberId: member.memberId, application });
    state.keys.set(key, application.applicationId);
    return HttpResponse.json(application, { status: 201 });
  }),

  http.put('/api/v1/me/instructor-applications/:applicationId', async ({ request, params }) => {
    const member = currentMockMember();
    if (!member) return apiError('UNAUTHENTICATED');
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const found = state.items.get(String(params.applicationId));
    if (!found || found.memberId !== member.memberId) return apiError('NOT_FOUND');
    if (!found.application.canEdit) return rule('심사가 진행되어 지원서를 고칠 수 없습니다.');
    const body = (await request.json()) as Schemas['InstructorApplyWrite'];
    const fields = validate(body);
    if (Object.keys(fields).length > 0) return apiError('VALIDATION_FAILED', fields);
    found.application = {
      ...found.application,
      desiredCourse: body.desiredCourse.trim(),
      categoryId: body.categoryId,
      categoryName: categoryName(body.categoryId)!,
      career: body.career.trim(),
    };
    return HttpResponse.json(found.application);
  }),
];