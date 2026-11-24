// 주민 앱의 라우트 표. 메뉴의 모든 경로는 실제 화면이고 없는 주소는 찾을 수 없음 화면이다
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';
import { RequireLogin } from '../components/RequireLogin';
import { Layout } from '../layout/Layout';
import { SERVICE_PAGE_HANDLE } from '../layout/SubLayout';
import { Home } from '../pages/Home';
import { NotFound } from '../pages/Placeholder';
import { ViewModeProvider } from '../view/ViewModeProvider';

// 화면은 주소로 들어갈 때 내려받는다(코드 리뷰 성능 중-5). 첫 화면의 진입 파일에는 틀과 첫 화면만 둔다
const ApplicationDonePage = lazy(() => import('../pages/apply/ApplicationDonePage').then((m) => ({ default: m.ApplicationDonePage })));
const ApplyPage = lazy(() => import('../pages/apply/ApplyPage').then((m) => ({ default: m.ApplyPage })));
const CategoryCoursesPage = lazy(() => import('../pages/courses/CategoryCoursesPage').then((m) => ({ default: m.CategoryCoursesPage })));
const CourseDetailPage = lazy(() => import('../pages/courses/CourseDetailPage').then((m) => ({ default: m.CourseDetailPage })));
const CourseListPage = lazy(() => import('../pages/courses/CourseListPage').then((m) => ({ default: m.CourseListPage })));
const CoursePlanPage = lazy(() => import('../pages/courses/CoursePlanPage').then((m) => ({ default: m.CoursePlanPage })));
const ContactPage = lazy(() => import('../pages/content/ContactPage').then((m) => ({ default: m.ContactPage })));
const FacilityPage = lazy(() => import('../pages/content/FacilityPage').then((m) => ({ default: m.FacilityPage })));
const ContentPage = lazy(() => import('../pages/content/ContentPage').then((m) => ({ default: m.ContentPage })));
const InquiryFormPage = lazy(() => import('../pages/community/InquiryFormPage').then((m) => ({ default: m.InquiryFormPage })));
const MyInquiriesPage = lazy(() => import('../pages/community/MyInquiriesPage').then((m) => ({ default: m.MyInquiriesPage })));
const MyReviewsPage = lazy(() => import('../pages/community/MyReviewsPage').then((m) => ({ default: m.MyReviewsPage })));
const QnaDetailPage = lazy(() => import('../pages/community/QnaDetailPage').then((m) => ({ default: m.QnaDetailPage })));
const QnaListPage = lazy(() => import('../pages/community/QnaListPage').then((m) => ({ default: m.QnaListPage })));
const ReviewDetailPage = lazy(() => import('../pages/community/ReviewDetailPage').then((m) => ({ default: m.ReviewDetailPage })));
const ReviewFormPage = lazy(() => import('../pages/community/ReviewFormPage').then((m) => ({ default: m.ReviewFormPage })));
const ReviewListPage = lazy(() => import('../pages/community/ReviewListPage').then((m) => ({ default: m.ReviewListPage })));
const InstructorApplyPage = lazy(() => import('../pages/instructors/InstructorApplyPage').then((m) => ({ default: m.InstructorApplyPage })));
const InstructorDetailPage = lazy(() => import('../pages/instructors/InstructorDetailPage').then((m) => ({ default: m.InstructorDetailPage })));
const InstructorListPage = lazy(() => import('../pages/instructors/InstructorListPage').then((m) => ({ default: m.InstructorListPage })));
const MyReductionDetailPage = lazy(() => import('../pages/reductions/MyReductionDetailPage').then((m) => ({ default: m.MyReductionDetailPage })));
const MyReductionsPage = lazy(() => import('../pages/reductions/MyReductionsPage').then((m) => ({ default: m.MyReductionsPage })));
const ReductionApplyPage = lazy(() => import('../pages/reductions/ReductionApplyPage').then((m) => ({ default: m.ReductionApplyPage })));
const MyInstructorApplicationsPage = lazy(() => import('../pages/instructors/MyInstructorApplicationsPage').then((m) => ({ default: m.MyInstructorApplicationsPage })));
const RecruitmentDetailPage = lazy(() => import('../pages/instructors/RecruitmentDetailPage').then((m) => ({ default: m.RecruitmentDetailPage })));
const RecruitmentListPage = lazy(() => import('../pages/instructors/RecruitmentListPage').then((m) => ({ default: m.RecruitmentListPage })));
const BoardListPage = lazy(() => import('../pages/board/BoardListPage').then((m) => ({ default: m.BoardListPage })));
const PostDetailPage = lazy(() => import('../pages/board/PostDetailPage').then((m) => ({ default: m.PostDetailPage })));
const ChangePasswordPage = lazy(() => import('../pages/account/ChangePasswordPage').then((m) => ({ default: m.ChangePasswordPage })));
const FindIdPage = lazy(() => import('../pages/account/FindIdPage').then((m) => ({ default: m.FindIdPage })));
const NameChangePage = lazy(() => import('../pages/account/NameChangePage').then((m) => ({ default: m.NameChangePage })));
const ProfilePage = lazy(() => import('../pages/account/ProfilePage').then((m) => ({ default: m.ProfilePage })));
const ResetPasswordPage = lazy(() => import('../pages/account/ResetPasswordPage').then((m) => ({ default: m.ResetPasswordPage })));
const WithdrawDonePage = lazy(() => import('../pages/account/WithdrawDonePage').then((m) => ({ default: m.WithdrawDonePage })));
const WithdrawPage = lazy(() => import('../pages/account/WithdrawPage').then((m) => ({ default: m.WithdrawPage })));
const ApplicationCancelledPage = lazy(() => import('../pages/me/ApplicationCancelledPage').then((m) => ({ default: m.ApplicationCancelledPage })));
const MyApplicationPage = lazy(() => import('../pages/me/MyApplicationPage').then((m) => ({ default: m.MyApplicationPage })));
const MyApplicationsPage = lazy(() => import('../pages/me/MyApplicationsPage').then((m) => ({ default: m.MyApplicationsPage })));
const MyRefundsPage = lazy(() => import('../pages/me/MyRefundsPage').then((m) => ({ default: m.MyRefundsPage })));
const ReceiptPage = lazy(() => import('../pages/me/ReceiptPage').then((m) => ({ default: m.ReceiptPage })));
const RefundApplyPage = lazy(() => import('../pages/me/RefundApplyPage').then((m) => ({ default: m.RefundApplyPage })));
const PaymentPage = lazy(() => import('../pages/payment/PaymentPage').then((m) => ({ default: m.PaymentPage })));
const PaymentResultPage = lazy(() => import('../pages/payment/PaymentResultPage').then((m) => ({ default: m.PaymentResultPage })));
const JoinCompletePage = lazy(() => import('../pages/member/JoinCompletePage').then((m) => ({ default: m.JoinCompletePage })));
const JoinFlowLayout = lazy(() => import('../pages/member/JoinFlow').then((m) => ({ default: m.JoinFlowLayout })));
const JoinInfoPage = lazy(() => import('../pages/member/JoinInfoPage').then((m) => ({ default: m.JoinInfoPage })));
const JoinTermsPage = lazy(() => import('../pages/member/JoinTermsPage').then((m) => ({ default: m.JoinTermsPage })));
const JoinVerifyPage = lazy(() => import('../pages/member/JoinVerifyPage').then((m) => ({ default: m.JoinVerifyPage })));
const LoginPage = lazy(() => import('../pages/member/LoginPage').then((m) => ({ default: m.LoginPage })));
const TermPage = lazy(() => import('../pages/member/TermPage').then((m) => ({ default: m.TermPage })));

function Root() {
  return (
    <ViewModeProvider>
      <Layout />
    </ViewModeProvider>
  );
}

export const routes: RouteObject[] = [
  {
    element: <Root />,
    children: [
      { index: true, element: <Home /> },
      { path: 'courses', element: <CourseListPage /> },
      { path: 'courses/open', element: <CourseListPage status="OPEN" /> },
      { path: 'courses/upcoming', element: <CourseListPage status="UPCOMING" /> },
      { path: 'courses/field/:categoryId', element: <CategoryCoursesPage />, handle: SERVICE_PAGE_HANDLE },
      { path: 'courses/:courseId', element: <CourseDetailPage />, handle: SERVICE_PAGE_HANDLE },
      { path: 'courses/:courseId/plan', element: <CoursePlanPage />, handle: SERVICE_PAGE_HANDLE },
      { path: 'guide/apply', element: <ContentPage slug="guide-apply" groupTitle="강좌정보" /> },
      { path: 'guide/refund', element: <ContentPage slug="guide-refund" groupTitle="강좌정보" /> },
      { path: 'center/history', element: <ContentPage slug="center-history" groupTitle="센터소개" /> },
      { path: 'center/facility', element: <FacilityPage /> },
      { path: 'center/contact', element: <ContactPage /> },
      ...(['notice', 'news', 'resources', 'gallery', 'faq'] as const).map((board) => ({
        path: `board/${board}`,
        element: <BoardListPage board={board} />,
      })),
      ...(['notice', 'news', 'resources', 'gallery'] as const).map((board) => ({
        path: `board/${board}/:postId`,
        element: <PostDetailPage board={board} />,
      })),      ...[
        ['board/qna', <QnaListPage />],
        ['board/qna/write', <InquiryFormPage mode="create" />],
        ['board/qna/:postId/edit', <InquiryFormPage mode="edit" />],
        ['board/qna/:postId', <QnaDetailPage />],
        ['board/review/write', <ReviewFormPage mode="create" />],
        ['board/review/:postId/edit', <ReviewFormPage mode="edit" />],
        ['me/inquiries', <MyInquiriesPage />],
        ['me/reviews', <MyReviewsPage />],
      ].map(([path, page]) => ({
        path: path as string,
        element: <RequireLogin>{page}</RequireLogin>,
      })),
      { path: 'board/review', element: <ReviewListPage /> },
      { path: 'board/review/:postId', element: <ReviewDetailPage /> },      { path: 'instructors', element: <InstructorListPage /> },
      { path: 'instructors/recruit', element: <RecruitmentListPage /> },
      { path: 'instructors/recruit/:recruitmentId', element: <RecruitmentDetailPage /> },
      { path: 'instructors/:instructorId', element: <InstructorDetailPage /> },
      ...[
        ['instructors/recruit/:recruitmentId/apply', <InstructorApplyPage mode="create" />],
        ['me/instructor-applications', <MyInstructorApplicationsPage />],
  ['me/reductions', <MyReductionsPage />],
  ['me/reductions/new', <ReductionApplyPage />],
  ['me/reductions/:reviewId', <MyReductionDetailPage />],
        ['me/instructor-applications/:applicationId/edit', <InstructorApplyPage mode="edit" />],
      ].map(([path, page]) => ({
        path: path as string,
        element: <RequireLogin>{page}</RequireLogin>,
        handle: SERVICE_PAGE_HANDLE,
      })),      { path: 'login', element: <LoginPage />, handle: SERVICE_PAGE_HANDLE },
      { path: 'find-id', element: <FindIdPage />, handle: SERVICE_PAGE_HANDLE },
      { path: 'withdraw/done', element: <WithdrawDonePage />, handle: SERVICE_PAGE_HANDLE },
      { path: 'reset-password', element: <ResetPasswordPage />, handle: SERVICE_PAGE_HANDLE },
      {
        path: 'apply/:courseId',
        element: (
          <RequireLogin>
            <ApplyPage />
          </RequireLogin>
        ),
        handle: SERVICE_PAGE_HANDLE,
      },
      {
        path: 'applications/:applicationId/done',
        element: (
          <RequireLogin>
            <ApplicationDonePage />
          </RequireLogin>
        ),
        handle: SERVICE_PAGE_HANDLE,
      },
      {
        path: 'payment/:applicationId',
        element: (
          <RequireLogin>
            <PaymentPage />
          </RequireLogin>
        ),
        handle: SERVICE_PAGE_HANDLE,
      },
      {
        path: 'payment/:applicationId/result',
        element: (
          <RequireLogin>
            <PaymentResultPage />
          </RequireLogin>
        ),
        handle: SERVICE_PAGE_HANDLE,
      },
      ...[
        ['me/applications', <MyApplicationsPage />],
        ['me/applications/:applicationId', <MyApplicationPage />],
        ['me/applications/:applicationId/cancelled', <ApplicationCancelledPage />],
        ['me/applications/:applicationId/refund', <RefundApplyPage />],
        ['me/receipts/:paymentId', <ReceiptPage />],
        ['me/refunds', <MyRefundsPage />],
        ['me/profile', <ProfilePage />],
        ['me/name-change', <NameChangePage />],
        ['me/password', <ChangePasswordPage />],
        ['me/withdraw', <WithdrawPage />],
      ].map(([path, page]) => ({
        path: path as string,
        element: <RequireLogin>{page}</RequireLogin>,
        handle: SERVICE_PAGE_HANDLE,
      })),      {
        path: 'join',
        element: <JoinFlowLayout />,
        handle: SERVICE_PAGE_HANDLE,
        children: [
          { index: true, element: <JoinTermsPage /> },
          { path: 'verify', element: <JoinVerifyPage /> },
          { path: 'info', element: <JoinInfoPage /> },
          { path: 'complete', element: <JoinCompletePage /> },
        ],
      },
      { path: 'terms/:slug', element: <TermPage />, handle: SERVICE_PAGE_HANDLE },
      { path: '*', element: <NotFound /> },
    ],
  },
];
