// 관리자 화면 경로 표. 경로가 여기 있으면 알려진 화면이고, 메뉴(권한 응답)에 없으면 접근 권한이 없는 화면이다
import type { ReactElement } from 'react';
import { ComingSoonPage } from '../pages/ComingSoonPage';

// 단계마다 이 표의 ComingSoonPage를 실제 화면으로 바꾼다. 마지막 단계에서 ComingSoonPage를 지운다.
export const SCREENS: Array<{ path: string; element: ReactElement }> = [
  '/dashboard',
  '/stats',
  '/edu/courses',
  '/edu/cycles',
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
].map((path) => ({ path, element: <ComingSoonPage /> }));