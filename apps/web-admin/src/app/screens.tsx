// 관리자 화면 경로 표. 경로가 여기 있으면 알려진 화면이고, 메뉴(권한 응답)에 없으면 접근 권한이 없는 화면이다
import { type ReactElement, lazy } from 'react';

// 화면은 주소로 들어갈 때 내려받는다(코드 리뷰 성능 중-5). 첫 화면의 진입 파일에는 틀과 첫 화면만 둔다
const BoardSettingsPage = lazy(() => import('../pages/board/BoardSettingsPage').then((m) => ({ default: m.BoardSettingsPage })));
const PostFormPage = lazy(() => import('../pages/board/PostFormPage').then((m) => ({ default: m.PostFormPage })));
const PostListPage = lazy(() => import('../pages/board/PostListPage').then((m) => ({ default: m.PostListPage })));
const ContentFormPage = lazy(() => import('../pages/content/ContentFormPage').then((m) => ({ default: m.ContentFormPage })));
const ContentListPage = lazy(() => import('../pages/content/ContentListPage').then((m) => ({ default: m.ContentListPage })));
const FileDetailPage = lazy(() => import('../pages/file/FileDetailPage').then((m) => ({ default: m.FileDetailPage })));
const FileListPage = lazy(() => import('../pages/file/FileListPage').then((m) => ({ default: m.FileListPage })));
const InquiryDetailPage = lazy(() => import('../pages/inquiry/InquiryDetailPage').then((m) => ({ default: m.InquiryDetailPage })));
const InquiryListPage = lazy(() => import('../pages/inquiry/InquiryListPage').then((m) => ({ default: m.InquiryListPage })));
const MemberDetailPage = lazy(() => import('../pages/member/MemberDetailPage').then((m) => ({ default: m.MemberDetailPage })));
const MemberListPage = lazy(() => import('../pages/member/MemberListPage').then((m) => ({ default: m.MemberListPage })));
const NameChangePage = lazy(() => import('../pages/member/NameChangePage').then((m) => ({ default: m.NameChangePage })));
const ReductionDetailPage = lazy(() => import('../pages/reduction/ReductionDetailPage').then((m) => ({ default: m.ReductionDetailPage })));
const ReductionHistoryPage = lazy(() => import('../pages/reduction/ReductionHistoryPage').then((m) => ({ default: m.ReductionHistoryPage })));
const ReductionListPage = lazy(() => import('../pages/reduction/ReductionListPage').then((m) => ({ default: m.ReductionListPage })));
const RetentionDetailPage = lazy(() => import('../pages/retention/RetentionDetailPage').then((m) => ({ default: m.RetentionDetailPage })));
const RetentionListPage = lazy(() => import('../pages/retention/RetentionListPage').then((m) => ({ default: m.RetentionListPage })));
const RoleDetailPage = lazy(() => import('../pages/role/RoleDetailPage').then((m) => ({ default: m.RoleDetailPage })));
const RoleFormPage = lazy(() => import('../pages/role/RoleFormPage').then((m) => ({ default: m.RoleFormPage })));
const RoleListPage = lazy(() => import('../pages/role/RoleListPage').then((m) => ({ default: m.RoleListPage })));
const ClassDetailPage = lazy(() => import('../pages/setting/ClassDetailPage').then((m) => ({ default: m.ClassDetailPage })));
const ClassListPage = lazy(() => import('../pages/setting/ClassListPage').then((m) => ({ default: m.ClassListPage })));
const CodePage = lazy(() => import('../pages/setting/CodePage').then((m) => ({ default: m.CodePage })));
const SettingDetailPage = lazy(() => import('../pages/setting/SettingDetailPage').then((m) => ({ default: m.SettingDetailPage })));
const SettingListPage = lazy(() => import('../pages/setting/SettingListPage').then((m) => ({ default: m.SettingListPage })));
const SmsDetailPage = lazy(() => import('../pages/sms/SmsDetailPage').then((m) => ({ default: m.SmsDetailPage })));
const SmsListPage = lazy(() => import('../pages/sms/SmsListPage').then((m) => ({ default: m.SmsListPage })));
const SmsSendPage = lazy(() => import('../pages/sms/SmsSendPage').then((m) => ({ default: m.SmsSendPage })));
const DashboardPage = lazy(() => import('../pages/stats/DashboardPage').then((m) => ({ default: m.DashboardPage })));
const SatisfactionDetailPage = lazy(() => import('../pages/stats/SatisfactionDetailPage').then((m) => ({ default: m.SatisfactionDetailPage })));
const SatisfactionFormPage = lazy(() => import('../pages/stats/SatisfactionFormPage').then((m) => ({ default: m.SatisfactionFormPage })));
const SatisfactionListPage = lazy(() => import('../pages/stats/SatisfactionListPage').then((m) => ({ default: m.SatisfactionListPage })));
const SourceDetailPage = lazy(() => import('../pages/stats/SourceDetailPage').then((m) => ({ default: m.SourceDetailPage })));
const SourceFormPage = lazy(() => import('../pages/stats/SourceFormPage').then((m) => ({ default: m.SourceFormPage })));
const SourceListPage = lazy(() => import('../pages/stats/SourceListPage').then((m) => ({ default: m.SourceListPage })));
const StatsPage = lazy(() => import('../pages/stats/StatsPage').then((m) => ({ default: m.StatsPage })));
const TermFormPage = lazy(() => import('../pages/term/TermFormPage').then((m) => ({ default: m.TermFormPage })));
const TermListPage = lazy(() => import('../pages/term/TermListPage').then((m) => ({ default: m.TermListPage })));
const AttendanceDetailPage = lazy(() => import('../pages/education/AttendanceDetailPage').then((m) => ({ default: m.AttendanceDetailPage })));
const AttendanceListPage = lazy(() => import('../pages/education/AttendanceListPage').then((m) => ({ default: m.AttendanceListPage })));
const CourseFormPage = lazy(() => import('../pages/education/CourseFormPage').then((m) => ({ default: m.CourseFormPage })));
const CourseListPage = lazy(() => import('../pages/education/CourseListPage').then((m) => ({ default: m.CourseListPage })));
const CycleFormPage = lazy(() => import('../pages/education/CycleFormPage').then((m) => ({ default: m.CycleFormPage })));
const CycleListPage = lazy(() => import('../pages/education/CycleListPage').then((m) => ({ default: m.CycleListPage })));
const FacilityFormPage = lazy(() => import('../pages/education/FacilityFormPage').then((m) => ({ default: m.FacilityFormPage })));
const FacilityListPage = lazy(() => import('../pages/education/FacilityListPage').then((m) => ({ default: m.FacilityListPage })));
const InstructorReviewFormPage = lazy(() => import('../pages/education/InstructorReviewFormPage').then((m) => ({ default: m.InstructorReviewFormPage })));
const InstructorReviewListPage = lazy(() => import('../pages/education/InstructorReviewListPage').then((m) => ({ default: m.InstructorReviewListPage })));
const ScheduleChangeFormPage = lazy(() => import('../pages/education/ScheduleChangeFormPage').then((m) => ({ default: m.ScheduleChangeFormPage })));
const ScheduleFormPage = lazy(() => import('../pages/education/ScheduleFormPage').then((m) => ({ default: m.ScheduleFormPage })));
const SchedulePage = lazy(() => import('../pages/education/SchedulePage').then((m) => ({ default: m.SchedulePage })));
const ApplicationDetailPage = lazy(() => import('../pages/payment/ApplicationDetailPage').then((m) => ({ default: m.ApplicationDetailPage })));
const ApplicationListPage = lazy(() => import('../pages/payment/ApplicationListPage').then((m) => ({ default: m.ApplicationListPage })));
const RefundDetailPage = lazy(() => import('../pages/payment/RefundDetailPage').then((m) => ({ default: m.RefundDetailPage })));
const RefundListPage = lazy(() => import('../pages/payment/RefundListPage').then((m) => ({ default: m.RefundListPage })));
const RefundReceivePage = lazy(() => import('../pages/payment/RefundReceivePage').then((m) => ({ default: m.RefundReceivePage })));
const TransactionDetailPage = lazy(() => import('../pages/payment/TransactionDetailPage').then((m) => ({ default: m.TransactionDetailPage })));
const TransactionListPage = lazy(() => import('../pages/payment/TransactionListPage').then((m) => ({ default: m.TransactionListPage })));
const WaitlistDetailPage = lazy(() => import('../pages/payment/WaitlistDetailPage').then((m) => ({ default: m.WaitlistDetailPage })));
const WaitlistPage = lazy(() => import('../pages/payment/WaitlistPage').then((m) => ({ default: m.WaitlistPage })));

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
  { path: '/mbr/name-changes', element: <NameChangePage /> },
  { path: '/mbr/posts', element: <PostListPage /> },
  { path: '/mbr/posts/new', element: <PostFormPage mode="create" /> },
  { path: '/mbr/posts/:postId', element: <PostFormPage mode="edit" /> },
  { path: '/mbr/boards', element: <BoardSettingsPage /> },
  { path: '/mbr/inquiries', element: <InquiryListPage /> },
  { path: '/mbr/inquiries/:inquiryId', element: <InquiryDetailPage /> },
  { path: '/mbr/contents', element: <ContentListPage /> },
  { path: '/mbr/contents/new', element: <ContentFormPage mode="create" /> },
  { path: '/mbr/contents/:contentId', element: <ContentFormPage mode="edit" /> },
  { path: '/mbr/terms', element: <TermListPage /> },
  { path: '/mbr/terms/new', element: <TermFormPage mode="create" /> },
  { path: '/mbr/terms/:versionId', element: <TermFormPage mode="edit" /> },
  { path: '/mbr/files', element: <FileListPage /> },
  { path: '/mbr/files/:fileId', element: <FileDetailPage /> },
  { path: '/dashboard', element: <DashboardPage /> },
  { path: '/stats', element: <StatsPage /> },
  { path: '/satisfaction-sources', element: <SatisfactionListPage /> },
  { path: '/satisfaction-sources/new', element: <SatisfactionFormPage /> },
  { path: '/satisfaction-sources/:sourceId', element: <SatisfactionDetailPage /> },
  { path: '/stats-sources', element: <SourceListPage /> },
  { path: '/stats-sources/new', element: <SourceFormPage /> },
  { path: '/stats-sources/:sourceId', element: <SourceDetailPage /> },
  { path: '/sys/sms', element: <SmsListPage /> },
  { path: '/sys/sms/new', element: <SmsSendPage /> },
  { path: '/sys/sms/:smsId', element: <SmsDetailPage /> },
  { path: '/sys/roles', element: <RoleListPage /> },
  { path: '/sys/roles/new', element: <RoleFormPage /> },
  { path: '/sys/roles/:assignmentId', element: <RoleDetailPage /> },
  { path: '/pay/reductions', element: <ReductionListPage /> },
  { path: '/pay/reductions/:reviewId', element: <ReductionDetailPage /> },
  { path: '/pay/reduction-history', element: <ReductionHistoryPage /> },
  { path: '/sys/settings', element: <SettingListPage /> },
  { path: '/sys/settings/:settingId', element: <SettingDetailPage /> },
  { path: '/sys/codes', element: <CodePage /> },
  { path: '/sys/retention', element: <RetentionListPage /> },
  { path: '/sys/retention/:itemId', element: <RetentionDetailPage /> },
  { path: '/sys/classes', element: <ClassListPage /> },
  { path: '/sys/classes/:classId', element: <ClassDetailPage /> },
  { path: '/pay/refunds', element: <RefundListPage /> },
  { path: '/pay/refunds/new', element: <RefundReceivePage /> },
  { path: '/pay/refunds/:refundId', element: <RefundDetailPage /> },
  { path: '/pay/waitlist', element: <WaitlistPage /> },
  { path: '/pay/waitlist/:courseId', element: <WaitlistDetailPage /> },
  { path: '/edu/facilities', element: <FacilityListPage /> },
  { path: '/edu/facilities/new', element: <FacilityFormPage mode="create" /> },
  { path: '/edu/facilities/:facilityId', element: <FacilityFormPage mode="edit" /> },
];
