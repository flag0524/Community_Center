// 화면이 쓰는 관리자 서버 상태 조회
import type { Schemas } from '@jori/api-client';
import { queryOptions } from '@tanstack/react-query';
import { getJson } from './http';

export type AdminSession = Schemas['AdminSession'];
export type AdminPermissions = Schemas['AdminPermissions'];
export type MenuGroup = Schemas['MenuGroup'];
export type MenuItem = Schemas['MenuItem'];

export const sessionQuery = queryOptions({
  queryKey: ['session'],
  queryFn: ({ signal }) => getJson<AdminSession>('/auth/session', signal),
  staleTime: Infinity,
});

export const permissionsQuery = queryOptions({
  queryKey: ['permissions'],
  queryFn: ({ signal }) => getJson<AdminPermissions>('/me/permissions', signal),
  staleTime: Infinity,
});