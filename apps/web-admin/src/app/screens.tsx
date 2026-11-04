// 관리자 화면 경로 표. 경로가 여기 있으면 알려진 화면이고, 메뉴(권한 응답)에 없으면 접근 권한이 없는 화면이다
import type { ReactElement } from 'react';
import { ComingSoonPage } from '../pages/ComingSoonPage';
import { CourseFormPage } from '../pages/education/CourseFormPage';
import { CourseListPage } from '../pages/education/CourseListPage';
import { CycleFormPage } from '../pages/education/CycleFormPage';
import { CycleListPage } from '../pages/education/CycleListPage';

// 단계마다 아래 임시 자리(ComingSoonPage)를 실제 화면으로 바꾼다. 마지막 단계에서 ComingSoonPage를 지운다.
const PENDING = [
  '/dashboard',
  '/stats',
  '/edu/schedules',
  '/edu/instructors',
  '/edu/facilities',
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
  ...PENDING.map((path) => ({ path, element: <ComingSoonPage /> })),
];
