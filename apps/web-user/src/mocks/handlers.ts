// 개발 서버와 시험이 함께 쓰는 모의 API 처리기. 아직 만들지 않은 경로는 정의하지 않는다
import { HttpResponse, http } from 'msw';
import { applicationHandlers } from './applications';
import { authHandlers } from './auth';
import { boardHandlers } from './board';
import { mockNow } from './clock';
import { communityHandlers } from './community';
import { CONTENTS } from './contents';
import { instructorHandlers } from './instructors';
import {
  buildCategories,
  buildCourseDetail,
  buildCoursePage,
  buildCoursePlan,
  buildHome,
  contact,
  findCourseSeed,
} from './fixtures';

const notFound = () =>
  HttpResponse.json(
    { code: 'NOT_FOUND', message: '요청한 정보를 찾을 수 없습니다.', requestId: 'mock-not-found-0001' },
    { status: 404 },
  );

const toNumber = (value: string | null): number | undefined => {
  if (value === null) return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : undefined;
};

export const handlers = [
  ...authHandlers,
  ...applicationHandlers,
  ...boardHandlers,
  ...communityHandlers,
  ...instructorHandlers,
  http.get('/api/v1/home', () => HttpResponse.json(buildHome(mockNow()))),
  http.get('/api/v1/site/contact', () => HttpResponse.json(contact)),
  http.get('/api/v1/contents/:slug', ({ params }) => {
    const document = CONTENTS[String(params.slug) as keyof typeof CONTENTS];
    return document ? HttpResponse.json(document) : notFound();
  }),
  http.get('/api/v1/categories', () => HttpResponse.json(buildCategories())),
  http.get('/api/v1/courses', ({ request }) => {
    const params = new URL(request.url).searchParams;
    return HttpResponse.json(
      buildCoursePage(
        {
          q: params.get('q'),
          categoryId: params.get('categoryId'),
          day: params.get('day'),
          status: params.get('status'),
          page: toNumber(params.get('page')),
          size: toNumber(params.get('size')),
        },
        mockNow(),
      ),
    );
  }),
  http.get('/api/v1/courses/:courseId', ({ params }) => {
    const seed = findCourseSeed(String(params.courseId));
    return seed ? HttpResponse.json(buildCourseDetail(seed, mockNow())) : notFound();
  }),
  http.get('/api/v1/courses/:courseId/plan', ({ params }) => {
    const seed = findCourseSeed(String(params.courseId));
    return seed ? HttpResponse.json(buildCoursePlan(seed)) : notFound();
  }),
];
