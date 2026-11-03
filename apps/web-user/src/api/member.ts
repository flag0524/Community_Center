// 회원정보 수정, 비밀번호 변경, 회원탈퇴 요청
import type { Schemas } from '@jori/api-client';
import { putJson, postJson, rememberCsrfToken } from './http';

export type MemberProfile = Schemas['MemberProfile'];

export const updateProfile = (body: Schemas['ProfileUpdate']) => putJson<MemberProfile>('/me/profile', body);

export async function changePassword(body: Schemas['PasswordChange']): Promise<void> {
  await putJson('/me/password', body);
  // 서버가 비밀번호를 바꾸며 토큰을 바꾼다. 다음 요청 때 세션에서 새로 받는다.
  rememberCsrfToken(null);
}

export async function withdraw(body: Schemas['WithdrawalRequest']): Promise<void> {
  await postJson('/me/withdraw', body);
  rememberCsrfToken(null);
}