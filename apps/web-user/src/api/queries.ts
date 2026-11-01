// 화면이 쓰는 서버 상태 조회. 기본 화면과 쉬운 화면이 같은 쿼리 키를 공유한다(RQ-QUR-NF-008)
import type { Schemas } from '@jori/api-client';
import { queryOptions } from '@tanstack/react-query';
import { toQueryString } from '../lib/queryString';
import { getJson } from './http';

export type HomeResponse = Schemas['HomeResponse'];
export type ContactResponse = Schemas['ContactResponse'];
export type CategoryList = Schemas['CategoryList'];
export type CoursePage = Schemas['CoursePage'];
export type CourseSummary = Schemas['CourseSummary'];
export type CourseDetail = Schemas['CourseDetail'];
export type CoursePlan = Schemas['CoursePlan'];

export const homeQuery = queryOptions({
  queryKey: ['home'],
  queryFn: ({ signal }) => getJson<HomeResponse>('/home', signal),
});

export const contactQuery = queryOptions({
  queryKey: ['site', 'contact'],
  queryFn: ({ signal }) => getJson<ContactResponse>('/site/contact', signal),
  staleTime: 5 * 60 * 1000,
});

export const categoriesQuery = queryOptions({
  queryKey: ['categories'],
  queryFn: ({ signal }) => getJson<CategoryList>('/categories', signal),
  staleTime: 5 * 60 * 1000,
});

/** 강좌 목록 조건. 주소의 쿼리와 같은 이름을 쓴다. */
export interface CourseListParams {
  q?: string;
  categoryId?: string;
  day?: Schemas['Weekday'];
  status?: Schemas['ReceptionState'];
  page?: number;
  size?: number;
}

export const courseListQuery = (params: CourseListParams) =>
  queryOptions({
    queryKey: ['courses', 'list', params],
    queryFn: ({ signal }) => getJson<CoursePage>(`/courses${toQueryString({ ...params })}`, signal),
  });

export const courseDetailQuery = (courseId: string) =>
  queryOptions({
    queryKey: ['courses', 'detail', courseId],
    queryFn: ({ signal }) => getJson<CourseDetail>(`/courses/${encodeURIComponent(courseId)}`, signal),
  });

export const coursePlanQuery = (courseId: string) =>
  queryOptions({
    queryKey: ['courses', 'plan', courseId],
    queryFn: ({ signal }) => getJson<CoursePlan>(`/courses/${encodeURIComponent(courseId)}/plan`, signal),
  });
