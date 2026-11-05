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
export type InstructorReviewPage = Schemas['InstructorReviewPage'];
export type InstructorReview = Schemas['InstructorReview'];
export type AttendancePage = Schemas['AttendancePage'];
export type AttendanceDetail = Schemas['AttendanceDetail'];
export type AdminApplicationPage = Schemas['AdminApplicationPage'];
export type AdminApplication = Schemas['AdminApplication'];
export type WaitlistPage = Schemas['WaitlistPage'];
export type WaitlistDetail = Schemas['WaitlistDetail'];
export type TransactionPage = Schemas['TransactionPage'];
export type Transaction = Schemas['Transaction'];

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
export interface InstructorReviewParams {
  q?: string;
  status?: Schemas['ReviewStatus'];
  isPublic?: 'true' | 'false';
  page?: number;
}

export const instructorReviewListQuery = (params: InstructorReviewParams) =>
  queryOptions({
    queryKey: ['reviews', 'list', params],
    queryFn: ({ signal }) =>
      getJson<InstructorReviewPage>(
        `/instructor-applications${toQueryString({ ...params, page: params.page && params.page > 1 ? params.page : undefined })}`,
        signal,
      ),
  });

export const instructorReviewQuery = (applicationId: string) =>
  queryOptions({
    queryKey: ['reviews', 'detail', applicationId],
    queryFn: ({ signal }) => getJson<InstructorReview>(`/instructor-applications/${encodeURIComponent(applicationId)}`, signal),
  });

export interface AttendanceParams {
  cycleId?: string;
  courseId?: string;
  classDate?: string;
  inputStatus?: Schemas['AttendanceInputStatus'];
  page?: number;
}

export const attendanceListQuery = (params: AttendanceParams) =>
  queryOptions({
    queryKey: ['attendance', 'list', params],
    queryFn: ({ signal }) =>
      getJson<AttendancePage>(`/attendance${toQueryString({ ...params, page: params.page && params.page > 1 ? params.page : undefined })}`, signal),
  });

export const attendanceQuery = (attendanceId: string) =>
  queryOptions({
    queryKey: ['attendance', 'detail', attendanceId],
    queryFn: ({ signal }) => getJson<AttendanceDetail>(`/attendance/${encodeURIComponent(attendanceId)}`, signal),
  });
export interface AdminApplicationParams {
  q?: string;
  cycleId?: string;
  courseId?: string;
  status?: Schemas['ApplicationStatus'];
  paymentStatus?: Schemas['PaymentStatus'];
  from?: string;
  to?: string;
  page?: number;
}

export const adminApplicationListQuery = (params: AdminApplicationParams) =>
  queryOptions({
    queryKey: ['applications', 'list', params],
    queryFn: ({ signal }) =>
      getJson<AdminApplicationPage>(`/applications${toQueryString({ ...params, page: params.page && params.page > 1 ? params.page : undefined })}`, signal),
  });

export const adminApplicationQuery = (applicationId: string) =>
  queryOptions({
    queryKey: ['applications', 'detail', applicationId],
    queryFn: ({ signal }) => getJson<AdminApplication>(`/applications/${encodeURIComponent(applicationId)}`, signal),
  });

export const waitlistQuery = (page: number) =>
  queryOptions({
    queryKey: ['waitlist', 'list', page],
    queryFn: ({ signal }) => getJson<WaitlistPage>(`/waitlist${toQueryString({ page: page > 1 ? page : undefined })}`, signal),
  });

export const waitlistDetailQuery = (courseId: string) =>
  queryOptions({
    queryKey: ['waitlist', 'detail', courseId],
    queryFn: ({ signal }) => getJson<WaitlistDetail>(`/waitlist/${encodeURIComponent(courseId)}`, signal),
  });
export interface TransactionParams {
  q?: string;
  status?: Schemas['PaymentStatus'];
  method?: Schemas['PaymentMethod'];
  from?: string;
  to?: string;
  conflictOnly?: 'true';
  page?: number;
}

export const transactionListQuery = (params: TransactionParams) =>
  queryOptions({
    queryKey: ['transactions', 'list', params],
    queryFn: ({ signal }) =>
      getJson<TransactionPage>(`/transactions${toQueryString({ ...params, page: params.page && params.page > 1 ? params.page : undefined })}`, signal),
  });

export const transactionQuery = (transactionId: string) =>
  queryOptions({
    queryKey: ['transactions', 'detail', transactionId],
    queryFn: ({ signal }) => getJson<Transaction>(`/transactions/${encodeURIComponent(transactionId)}`, signal),
  });
