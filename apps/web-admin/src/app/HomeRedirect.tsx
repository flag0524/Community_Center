// 처음 화면. 권한 응답의 첫 메뉴 항목으로 보내고, 보이는 메뉴가 하나도 없으면 권한 없음 화면을 보인다
import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { permissionsQuery } from '../api/queries';
import { ForbiddenPage } from '../pages/StatusPages';

export function HomeRedirect() {
  const { data } = useQuery(permissionsQuery);
  if (!data) return null;
  const first = data.menu[0]?.items[0];
  return first ? <Navigate to={first.path} replace /> : <ForbiddenPage />;
}