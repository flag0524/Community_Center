// 관리자 앱의 라우트 표. 로그인 화면 밖의 모든 화면은 로그인과 메뉴 권한을 거친다
import type { RouteObject } from 'react-router-dom';
import { AdminLayout } from '../layout/AdminLayout';
import { LoginPage } from '../pages/LoginPage';
import { NotFoundPage } from '../pages/StatusPages';
import { HomeRedirect } from './HomeRedirect';
import { PermissionGate } from './PermissionGate';
import { RequireAdmin } from './RequireAdmin';
import { SCREENS } from './screens';

export const routes: RouteObject[] = [
  { path: 'login', element: <LoginPage /> },
  {
    element: (
      <RequireAdmin>
        <AdminLayout />
      </RequireAdmin>
    ),
    children: [
      { index: true, element: <HomeRedirect /> },
      ...SCREENS.map(({ path, element }) => ({ path, element: <PermissionGate>{element}</PermissionGate> })),
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];