// 주민 앱의 라우트 표. 이식된 화면은 실제 컴포넌트를, 나머지는 임시 화면을 연결한다
import type { RouteObject } from 'react-router-dom';
import { RequireLogin } from '../components/RequireLogin';
import { Layout } from '../layout/Layout';
import { EXTRA_PLACEHOLDERS, FOOTER_LINKS, NAV_GROUPS, EASY_NAV } from '../layout/navigation';
import { SERVICE_PAGE_HANDLE } from '../layout/SubLayout';
import { ApplicationDonePage } from '../pages/apply/ApplicationDonePage';
import { ApplyPage } from '../pages/apply/ApplyPage';
import { CategoryCoursesPage } from '../pages/courses/CategoryCoursesPage';
import { CourseDetailPage } from '../pages/courses/CourseDetailPage';
import { CourseListPage } from '../pages/courses/CourseListPage';
import { CoursePlanPage } from '../pages/courses/CoursePlanPage';
import { Home } from '../pages/Home';
import { ApplicationCancelledPage } from '../pages/me/ApplicationCancelledPage';
import { MyApplicationPage } from '../pages/me/MyApplicationPage';
import { MyApplicationsPage } from '../pages/me/MyApplicationsPage';
import { MyRefundsPage } from '../pages/me/MyRefundsPage';
import { ReceiptPage } from '../pages/me/ReceiptPage';
import { RefundApplyPage } from '../pages/me/RefundApplyPage';
import { PaymentPage } from '../pages/payment/PaymentPage';
import { PaymentResultPage } from '../pages/payment/PaymentResultPage';
import { JoinCompletePage } from '../pages/member/JoinCompletePage';
import { JoinFlowLayout } from '../pages/member/JoinFlow';
import { JoinInfoPage } from '../pages/member/JoinInfoPage';
import { JoinTermsPage } from '../pages/member/JoinTermsPage';
import { JoinVerifyPage } from '../pages/member/JoinVerifyPage';
import { LoginPage } from '../pages/member/LoginPage';
import { TermPage } from '../pages/member/TermPage';
import { NotFound, Placeholder } from '../pages/Placeholder';
import { ViewModeProvider } from '../view/ViewModeProvider';

// 실제 화면으로 옮긴 경로. 임시 화면 목록에서 뺀다.
const IMPLEMENTED_PATHS = new Set([
  '/courses',
  '/courses/open',
  '/courses/upcoming',
  '/me/applications',
  '/terms/terms-of-use',
  '/terms/privacy-policy',
  '/terms/email-refusal',
]);

function placeholderRoutes(): RouteObject[] {
  const byPath = new Map<string, string>();
  for (const group of NAV_GROUPS) {
    byPath.set(group.to, byPath.get(group.to) ?? group.items.find((item) => item.to === group.to)?.label ?? group.title);
    for (const item of group.items) byPath.set(item.to, item.label);
  }
  for (const item of [...EASY_NAV, ...FOOTER_LINKS, ...EXTRA_PLACEHOLDERS]) {
    if (!byPath.has(item.to)) byPath.set(item.to, item.label);
  }
  return [...byPath]
    .filter(([path]) => !IMPLEMENTED_PATHS.has(path))
    .map(([path, title]) => ({ path, element: <Placeholder title={title} /> }));
}

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
      { path: 'login', element: <LoginPage />, handle: SERVICE_PAGE_HANDLE },
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
      ...placeholderRoutes(),
      { path: '*', element: <NotFound /> },
    ],
  },
];
