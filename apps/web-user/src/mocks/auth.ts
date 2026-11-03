// 로그인·세션·본인확인 OTP·가입·약관을 흉내 내는 모의 서버. 상태는 메모리에만 두고 시험마다 되돌린다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { TERMS } from './terms';

type ErrorCode = Schemas['ErrorCode'];
type MemberBrief = Schemas['MemberBrief'];
type OtpRequest = Schemas['OtpRequest'];
type OtpVerifyRequest = Schemas['OtpVerifyRequest'];
type LoginRequest = Schemas['LoginRequest'];
type JoinRequest = Schemas['JoinRequest'];

/** 시험·시연용 가상 값. 화면 어디에도 노출하지 않는다. */
export const DEMO = {
  loginId: 'demo-member',
  password: 'Demo-pass-2026',
  otpCode: '123456',
  member: { memberId: '1000000000000000000001', name: '예시회원', loginId: 'demo-member' } satisfies MemberBrief,
} as const;

const LOGIN_FAILURE_LIMIT = 5;
const OTP_FAILURE_LIMIT = 5;
const OTP_VALID_SECONDS = 300;
const OTP_RESEND_SECONDS = 60;
const IDLE_TIMEOUT_SECONDS = 1800;

interface Cert {
  name: string;
  failures: number;
  verified: boolean;
  issuedAt: number;
}

interface MockAuthState {
  csrfSeq: number;
  member: MemberBrief | null;
  loginFailures: Map<string, number>;
  certs: Map<string, Cert>;
  certSeq: number;
  lastOtpAt: number | null;
  members: Map<string, MemberBrief>;
  passwords: Map<string, string>;
  memberSeq: number;
}

const initialState = (): MockAuthState => ({
  csrfSeq: 1,
  member: null,
  loginFailures: new Map(),
  certs: new Map(),
  certSeq: 0,
  lastOtpAt: null,
  members: new Map([[DEMO.loginId, { ...DEMO.member }]]),
  passwords: new Map([[DEMO.loginId, DEMO.password]]),
  memberSeq: 1,
});

let state = initialState();

/** 시험 사이에 세션·인증번호·가입 이력을 처음으로 되돌린다. */
export function resetMockAuth(): void {
  state = initialState();
}

const MESSAGES: Partial<Record<ErrorCode, string>> = {
  VALIDATION_FAILED: '입력 형식이 올바르지 않습니다.',
  FORBIDDEN: '요청을 확인할 수 없습니다. 화면을 새로 열고 다시 시도해 주세요.',
  NOT_FOUND: '요청한 정보를 찾을 수 없습니다.',
  LOGIN_FAILED: '아이디 또는 비밀번호를 확인해 주세요.',
  LOGIN_LOCKED: '로그인 시도가 많아 잠시 이용할 수 없습니다.',
  OTP_INVALID: '인증번호가 올바르지 않습니다.',
  OTP_EXPIRED: '인증번호 유효시간이 지났습니다. 다시 요청해 주세요.',
  OTP_RESEND_TOO_SOON: '인증번호는 잠시 후 다시 요청할 수 있습니다.',
  JOIN_LOGIN_ID_TAKEN: '이미 사용 중인 아이디입니다.',
  UNAUTHENTICATED: '로그인이 필요합니다.',
  IDEMPOTENCY_CONFLICT: '같은 요청 키로 다른 내용이 전달되었습니다.',
  APLY_RCPT_CLOSED: '접수기간이 아닙니다.',
  APLY_ALREADY_APPLIED: '이미 신청한 강좌입니다.',
};

const STATUS: Partial<Record<ErrorCode, number>> = {
  VALIDATION_FAILED: 400,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  LOGIN_FAILED: 401,
  LOGIN_LOCKED: 429,
  OTP_INVALID: 422,
  OTP_EXPIRED: 422,
  OTP_RESEND_TOO_SOON: 429,
  JOIN_LOGIN_ID_TAKEN: 422,
  UNAUTHENTICATED: 401,
  IDEMPOTENCY_CONFLICT: 409,
  APLY_RCPT_CLOSED: 422,
  APLY_ALREADY_APPLIED: 422,
};

export function apiError(code: ErrorCode, fields?: Record<string, string>) {
  return HttpResponse.json(
    { code, message: MESSAGES[code] ?? code, fields: fields ?? null, requestId: `mock-${code.toLowerCase()}-0001` },
    { status: STATUS[code] ?? 400 },
  );
}

/** 지금 로그인한 모의 회원. 로그인하지 않았으면 null이다. */
export const currentMockMember = (): MemberBrief | null => state.member;
export const csrfRejected = (request: Request) => request.headers.get('X-CSRF-Token') !== csrfToken();

const csrfToken = () => `mock-csrf-${state.csrfSeq}`;
const rotateCsrf = () => {
  state.csrfSeq += 1;
};
const serverNow = () => new Date().toISOString();
const sessionBody = () => ({
  authenticated: state.member !== null,
  csrfToken: csrfToken(),
  member: state.member,
  idleTimeoutSeconds: state.member ? IDLE_TIMEOUT_SECONDS : null,
  serverNow: serverNow(),
});

const serialOf = (seq: number) => String(1_000_000_000_000_000_000_000n + BigInt(seq)).padStart(22, '0');

const PHONE = /^01[0-9]{8,9}$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export const authHandlers = [
  http.get('/api/v1/auth/session', () => HttpResponse.json(sessionBody())),

  http.post('/api/v1/auth/login', async ({ request }) => {
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const { loginId, password } = (await request.json()) as LoginRequest;
    const failures = state.loginFailures.get(loginId) ?? 0;
    if (failures >= LOGIN_FAILURE_LIMIT) return apiError('LOGIN_LOCKED');
    const member = state.members.get(loginId);
    if (!member || state.passwords.get(loginId) !== password) {
      state.loginFailures.set(loginId, failures + 1);
      return apiError('LOGIN_FAILED');
    }
    state.loginFailures.delete(loginId);
    state.member = member;
    rotateCsrf();
    return HttpResponse.json(sessionBody());
  }),

  http.post('/api/v1/auth/logout', ({ request }) => {
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    state.member = null;
    rotateCsrf();
    return new HttpResponse(null, { status: 204 });
  }),

  http.post('/api/v1/auth/otp', async ({ request }) => {
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const body = (await request.json()) as OtpRequest;
    if (!PHONE.test(body.phone)) return apiError('VALIDATION_FAILED', { phone: '휴대전화 번호 형식을 확인해 주세요.' });
    const now = Date.now();
    if (state.lastOtpAt !== null && now - state.lastOtpAt < OTP_RESEND_SECONDS * 1000) {
      return apiError('OTP_RESEND_TOO_SOON');
    }
    state.lastOtpAt = now;
    state.certSeq += 1;
    const certRequestId = serialOf(state.certSeq);
    state.certs.set(certRequestId, { name: body.name ?? DEMO.member.name, failures: 0, verified: false, issuedAt: now });
    return HttpResponse.json({
      certRequestId,
      expiresAt: new Date(now + OTP_VALID_SECONDS * 1000).toISOString(),
      resendAvailableAt: new Date(now + OTP_RESEND_SECONDS * 1000).toISOString(),
      serverNow: new Date(now).toISOString(),
    });
  }),

  http.post('/api/v1/auth/otp/verify', async ({ request }) => {
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const { certRequestId, code } = (await request.json()) as OtpVerifyRequest;
    const cert = state.certs.get(certRequestId);
    if (!cert || cert.failures >= OTP_FAILURE_LIMIT) return apiError('OTP_INVALID');
    if (Date.now() - cert.issuedAt > OTP_VALID_SECONDS * 1000) return apiError('OTP_EXPIRED');
    if (code !== DEMO.otpCode) {
      cert.failures += 1;
      return HttpResponse.json({ verified: false, remainingAttempts: OTP_FAILURE_LIMIT - cert.failures });
    }
    cert.verified = true;
    return HttpResponse.json({ verified: true });
  }),

  http.get('/api/v1/join/check-id', ({ request }) => {
    const loginId = new URL(request.url).searchParams.get('loginId') ?? '';
    return HttpResponse.json({ available: !state.members.has(loginId) });
  }),

  http.post('/api/v1/join', async ({ request }) => {
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const body = (await request.json()) as JoinRequest;
    const cert = state.certs.get(body.certRequestId);
    if (!cert?.verified || body.code !== DEMO.otpCode) return apiError('OTP_INVALID');
    const fields: Record<string, string> = {};
    if (body.password.length < 10) fields.password = '비밀번호는 10자 이상이어야 합니다.';
    if (!EMAIL.test(body.email)) fields.email = '이메일 형식을 확인해 주세요.';
    if (Object.keys(fields).length > 0) return apiError('VALIDATION_FAILED', fields);
    if (state.members.has(body.loginId)) return apiError('JOIN_LOGIN_ID_TAKEN', { loginId: MESSAGES.JOIN_LOGIN_ID_TAKEN! });
    state.memberSeq += 1;
    const member: MemberBrief = { memberId: serialOf(1000 + state.memberSeq), name: cert.name, loginId: body.loginId };
    state.members.set(body.loginId, member);
    state.passwords.set(body.loginId, body.password);
    state.certs.delete(body.certRequestId);
    return HttpResponse.json(member, { status: 201 });
  }),

  http.get('/api/v1/terms/:termType', ({ params }) => {
    const term = TERMS[String(params.termType) as keyof typeof TERMS];
    return term ? HttpResponse.json(term) : apiError('NOT_FOUND');
  }),
];
