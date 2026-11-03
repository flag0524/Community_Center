// 로그인한 회원만 볼 수 있는 화면을 감싼다. 로그인하지 않았으면 로그인으로 보내고 돌아올 주소를 남긴다
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { sessionQuery } from '../api/queries';
import { QueryFallback } from './QueryFallback';

export function RequireLogin({ children }: { children: ReactNode }) {
  const session = useQuery(sessionQuery);
  const { pathname, search } = useLocation();

  if (!session.data) return <QueryFallback query={session} what="로그인 정보" />;
  if (!session.data.authenticated) {
    return <Navigate to={`/login?next=${encodeURIComponent(pathname + search)}`} replace />;
  }
  return children;
}
