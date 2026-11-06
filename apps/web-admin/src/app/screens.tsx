// 관리자 화면 경로 표. 경로가 여기 있으면 알려진 화면이고, 메뉴(권한 응답)에 없으면 접근 권한이 없는 화면이다
import type { ReactElement } from 'react';
import { ComingSoonPage } from '../pages/ComingSoonPage';
import { BoardSettingsPage } from '../pages/board/BoardSettingsPage';
import { PostFormPage } from '../pages/board/PostFormPage';
import { PostListPage } from '../pages/board/PostListPage';
import { ContentFormPage } from '../pages/content/ContentFormPage';
import { ContentListPage } from '../pages/content/ContentListPage';
import { InquiryDetailPage } from '../pages/inquiry/InquiryDetailPage';
import { InquiryListPage } from '../pages/inquiry/InquiryListPage';
import { MemberDetailPage } from '../pages/member/MemberDetailPage';
import { MemberListPage } from '../pages/member/MemberListPage';
import { AttendanceDetailPage } from '../pages/education/AttendanceDetailPage';
import { AttendanceListPage } from '../pages/education/AttendanceListPage';
import { CourseFormPage } from '../pages/education/CourseFormPage';
import { CourseListPage } from '../pages/education/CourseListPage';
import { CycleFormPage } from '../pages/education/CycleFormPage';
import { CycleListPage } from '../pages/education/CycleListPage';
import { FacilityFormPage } from '../pages/education/FacilityFormPage';
import { FacilityListPage } from '../pages/education/FacilityListPage';
import { InstructorReviewFormPage } from '../pages/education/InstructorReviewFormPage';
import { InstructorReviewListPage } from '../pages/education/InstructorReviewListPage';
import { ScheduleChangeFormPage } from '../pages/education/ScheduleChangeFormPage';
import { ScheduleFormPage } from '../pages/education/ScheduleFormPage';
import { SchedulePage } from '../pages/education/SchedulePage';
import { ApplicationDetailPage } from '../pages/payment/ApplicationDetailPage';
import { ApplicationListPage } from '../pages/payment/ApplicationListPage';
import { RefundDetailPage } from '../pages/payment/RefundDetailPage';
import { RefundListPage } from '../pages/payment/RefundListPage';
import { RefundReceivePage } from '../pages/payment/RefundReceivePage';
import { TransactionDetailPage } from '../pages/payment/TransactionDetailPage';
import { TransactionListPage } from '../pages/payment/TransactionListPage';
import { WaitlistDetailPage } from '../pages/payment/WaitlistDetailPage';
import { WaitlistPage } from '../pages/payment/WaitlistPage';

// 단계마다 아래 임시 자리(ComingSoonPage)를 실제 화면으로 바꾼다. 마지막 단계에서 ComingSoonPage를 지운다.
const PENDING = [
  '/dashboard',
  '/stats',
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
  { path: '/edu/instructors', element: <InstructorReviewListPage /> },
  { path: '/edu/instructors/new', element: <InstructorReviewFormPage mode="create" /> },
  { path: '/edu/instructors/:applicationId', element: <InstructorReviewFormPage mode="review" /> },
  { path: '/edu/attendance', element: <AttendanceListPage /> },
  { path: '/edu/attendance/:attendanceId', element: <AttendanceDetailPage /> },
  { path: '/pay/applications', element: <ApplicationListPage /> },
  { path: '/pay/applications/:applicationId', element: <ApplicationDetailPage /> },
  { path: '/pay/transactions', element: <TransactionListPage /> },
  { path: '/pay/transactions/:transactionId', element: <TransactionDetailPage /> },
  { path: '/mbr/members', element: <MemberListPage /> },
  { path: '/mbr/members/:memberId', element: <MemberDetailPage /> },
  { path: '/mbr/posts', element: <PostListPage /> },
  { path: '/mbr/posts/new', element: <PostFormPage mode="create" /> },
  { path: '/mbr/posts/:postId', element: <PostFormPage mode="edit" /> },
  { path: '/mbr/boards', element: <BoardSettingsPage /> },
  { path: '/mbr/inquiries', element: <InquiryListPage /> },
  { path: '/mbr/inquiries/:inquiryId', element: <InquiryDetailPage /> },
  { path: '/mbr/contents', element: <ContentListPage /> },
  { path: '/mbr/contents/new', element: <ContentFormPage mode="create" /> },
  { path: '/mbr/contents/:contentId', element: <ContentFormPage mode="edit" /> },
  { path: '/pay/refunds', element: <RefundListPage /> },
  { path: '/pay/refunds/new', element: <RefundReceivePage /> },
  { path: '/pay/refunds/:refundId', element: <RefundDetailPage /> },
  { path: '/pay/waitlist', element: <WaitlistPage /> },
  { path: '/pay/waitlist/:courseId', element: <WaitlistDetailPage /> },
  { path: '/edu/facilities', element: <FacilityListPage /> },
  { path: '/edu/facilities/new', element: <FacilityFormPage mode="create" /> },
  { path: '/edu/facilities/:facilityId', element: <FacilityFormPage mode="edit" /> },
  ...PENDING.map((path) => ({ path, element: <ComingSoonPage /> })),
];
