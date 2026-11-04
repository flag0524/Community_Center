// 화면이 쓰는 관리자 서버 상태 조회
import type { Schemas } from '@jori/api-client';
import { queryOptions } from '@tanstack/react-query';
import { toQueryString } from '../lib/queryString';
import { getJson } from './http';

export type AdminSession = Schemas['AdminSession'];
export type AdminPermissions = Schemas['AdminPermissions'];
export type MenuGroup = Schemas['MenuGroup'];
export type MenuItem = Schemas['MenuItem'];
export type CyclePage = Schemas['CyclePage'];
export type Cycle = Schemas['Cycle'];
export type CourseOptions = Schemas['CourseOptions'];
export type AdminCoursePage = Schemas['AdminCoursePage'];
export type AdminCourse = Schemas['AdminCourse'];
export type CancelPreview = Schemas['CancelPreview'];
export type FacilityList = Schemas['FacilityList'];
export type Facility = Schemas['Facility'];
export type CourseSchedules = Schemas['CourseSchedules'];

export const sessionQuery = queryOptions({
  queryKey: ['session'],
  queryFn: ({ signal }) => getJson<AdminSession>('/auth/session', signal),
  staleTime: Infinity,
});

export const permissionsQuery = queryOptions({
  queryKey: ['permissions'],
  queryFn: ({ signal }) => getJson<AdminPermissions>('/me/permissions', signal),
  staleTime: Infinity,
});
export const cycleListQuery = (page: number) =>
  queryOptions({
    queryKey: ['cycles', 'list', page],
    queryFn: ({ signal }) => getJson<CyclePage>(`/cycles?page=${page}&size=20`, signal),
  });

export const cycleQuery = (cycleId: string) =>
  queryOptions({
    queryKey: ['cycles', 'detail', cycleId],
    queryFn: ({ signal }) => getJson<Cycle>(`/cycles/${encodeURIComponent(cycleId)}`, signal),
  });

export const courseOptionsQuery = queryOptions({
  queryKey: ['course-options'],
  queryFn: ({ signal }) => getJson<CourseOptions>('/course-options', signal),
});

/** 강좌 목록 조건. 주소의 쿼리와 같은 이름을 쓴다. */
export interface AdminCourseParams {
  q?: string;
  cycleId?: string;
  classId?: string;
  dongId?: string;
  status?: Schemas['CourseAdminStatus'];
  page?: number;
  /** 선택 목록처럼 한꺼번에 받을 때만 쓴다. 비우면 서버 기본 크기다. */
  size?: number;
}

export const adminCourseListQuery = (params: AdminCourseParams) =>
  queryOptions({
    queryKey: ['courses', 'list', params],
    queryFn: ({ signal }) =>
      getJson<AdminCoursePage>(
        `/courses${toQueryString({ ...params, page: params.page && params.page > 1 ? params.page : undefined })}`,
        signal,
      ),
  });

export const adminCourseQuery = (courseId: string) =>
  queryOptions({
    queryKey: ['courses', 'detail', courseId],
    queryFn: ({ signal }) => getJson<AdminCourse>(`/courses/${encodeURIComponent(courseId)}`, signal),
  });

export const cancelPreviewQuery = (courseId: string) =>
  queryOptions({
    queryKey: ['courses', 'cancel-preview', courseId],
    queryFn: ({ signal }) => getJson<CancelPreview>(`/courses/${encodeURIComponent(courseId)}/cancel-preview`, signal),
    gcTime: 0,
  });
export const facilityListQuery = queryOptions({
  queryKey: ['facilities', 'list'],
  queryFn: ({ signal }) => getJson<FacilityList>('/facilities', signal),
});

export const facilityQuery = (facilityId: string) =>
  queryOptions({
    queryKey: ['facilities', 'detail', facilityId],
    queryFn: ({ signal }) => getJson<Facility>(`/facilities/${encodeURIComponent(facilityId)}`, signal),
  });

export const courseSchedulesQuery = (courseId: string) =>
  queryOptions({
    queryKey: ['schedules', courseId],
    queryFn: ({ signal }) => getJson<CourseSchedules>(`/courses/${encodeURIComponent(courseId)}/schedules`, signal),
  });
