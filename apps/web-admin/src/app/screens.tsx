// 관리자 화면 경로 표. 경로가 여기 있으면 알려진 화면이고, 메뉴(권한 응답)에 없으면 접근 권한이 없는 화면이다
import type { ReactElement } from 'react';
import { ComingSoonPage } from '../pages/ComingSoonPage';
import { CourseFormPage } from '../pages/education/CourseFormPage';
import { CourseListPage } from '../pages/education/CourseListPage';
import { CycleFormPage } from '../pages/education/CycleFormPage';
import { CycleListPage } from '../pages/education/CycleListPage';
import { FacilityFormPage } from '../pages/education/FacilityFormPage';
import { FacilityListPage } from '../pages/education/FacilityListPage';
import { ScheduleChangeFormPage } from '../pages/education/ScheduleChangeFormPage';
import { ScheduleFormPage } from '../pages/education/ScheduleFormPage';
import { SchedulePage } from '../pages/education/SchedulePage';

// 단계마다 아래 임시 자리(ComingSoonPage)를 실제 화면으로 바꾼다. 마지막 단계에서 ComingSoonPage를 지운다.
const PENDING = [
  '/dashboard',
  '/stats',
  '/edu/instructors',
  '/edu/attendance',
  '/pay/applications',
  '/pay/waitlist',
  '/pay/transactions',
  '/pay/refunds',
  '/mbr/members',
  '/mbr/posts',
  '/mbr/inquiries',
  '/mbr/contents',
  '/mbr/terms',
  '/mbr/files',
  '/sys/sms',
  '/sys/roles',
];

export const SCREENS: Array<{ path: string; element: ReactElement }> = [
  { path: '/edu/courses', element: <CourseListPage /> },
  { path: '/edu/courses/new', element: <CourseFormPage mode="create" /> },
  { path: '/edu/courses/:courseId', element: <CourseFormPage mode="edit" /> },
  { path: '/edu/cycles', element: <CycleListPage /> },
  { path: '/edu/cycles/new', element: <CycleFormPage mode="create" /> },
  { path: '/edu/cycles/:cycleId', element: <CycleFormPage mode="edit" /> },
  { path: '/edu/schedules', element: <SchedulePage /> },
  { path: '/edu/schedules/:courseId/new', element: <ScheduleFormPage mode="create" /> },
  { path: '/edu/schedules/:courseId/changes/new', element: <ScheduleChangeFormPage /> },
  { path: '/edu/schedules/:courseId/:scheduleId', element: <ScheduleFormPage mode="edit" /> },
  { path: '/edu/facilities', element: <FacilityListPage /> },
  { path: '/edu/facilities/new', element: <FacilityFormPage mode="create" /> },
  { path: '/edu/facilities/:facilityId', element: <FacilityFormPage mode="edit" /> },
  ...PENDING.map((path) => ({ path, element: <ComingSoonPage /> })),
];
