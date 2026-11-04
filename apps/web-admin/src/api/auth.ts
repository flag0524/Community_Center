// 관리자 로그인·로그아웃·세션 연장 요청. 화면은 이 함수만 거쳐 서버와 이야기한다
import type { Schemas } from '@jori/api-client';
import { postJson, rememberCsrfToken } from './http';
import type { AdminSession } from './queries';

export const login = (body: Schemas['AdminLoginRequest']) => postJson<AdminSession>('/auth/login', body);

export const extendSession = () => postJson<AdminSession>('/auth/extend');

export async function logout(): Promise<void> {
  await postJson('/auth/logout');
  // 로그아웃하면 서버가 토큰을 바꾼다. 다음 요청 때 세션에서 새로 받는다.
  rememberCsrfToken(null);
}