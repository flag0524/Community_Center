// 메뉴(권한 응답)에 있는 경로만 보여 주고 없으면 권한 없음 화면을 보이는 가드. 서버는 요청마다 다시 판정한다
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { permissionsQuery } from '../api/queries';
import { findItem } from '../layout/menu';
import { ForbiddenPage } from '../pages/StatusPages';

export function PermissionGate({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const { data } = useQuery(permissionsQuery);
  if (!data) return null;
  return findItem(data.menu, pathname) ? <>{children}</> : <ForbiddenPage />;
}