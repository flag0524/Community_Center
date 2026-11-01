// 로그인·로그아웃·본인확인·가입 요청. 화면은 이 함수만 거쳐 서버와 이야기한다
import type { Schemas } from '@jori/api-client';
import { getJson, postJson, rememberCsrfToken } from './http';
import type { SessionInfo } from './queries';

export type OtpIssued = Schemas['OtpIssued'];
export type OtpVerifyResult = Schemas['OtpVerifyResult'];
export type JoinRequest = Schemas['JoinRequest'];
export type MemberBrief = Schemas['MemberBrief'];

export const login = (body: Schemas['LoginRequest']) => postJson<SessionInfo>('/auth/login', body);

export async function logout(): Promise<void> {
  await postJson('/auth/logout');
  // 로그아웃하면 서버가 토큰을 바꾼다. 다음 요청 때 세션에서 새로 받는다.
  rememberCsrfToken(null);
}

export const requestJoinOtp = (phone: string, name: string) =>
  postJson<OtpIssued>('/auth/otp', { purpose: 'JOIN', phone, name });

export const verifyOtp = (certRequestId: string, code: string) =>
  postJson<OtpVerifyResult>('/auth/otp/verify', { certRequestId, code });

export const checkLoginId = (loginId: string) =>
  getJson<Schemas['LoginIdCheck']>(`/join/check-id?loginId=${encodeURIComponent(loginId)}`);

export const join = (body: JoinRequest) => postJson<MemberBrief>('/join', body);
