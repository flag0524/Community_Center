// 관리자 로그인 상태를 확인하고, 로그인하지 않았으면 돌아올 주소를 남기고 로그인으로 보내는 가드
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { sessionQuery } from '../api/queries';

export function RequireAdmin({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { data, isPending, isError } = useQuery(sessionQuery);
  if (isPending) return <p className="adm-loading" role="status">불러오는 중입니다.</p>;
  if (isError) return <p className="adm-loading" role="alert">서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.</p>;
  if (!data.authenticated) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}