// 관리자 로그인·세션·권한(메뉴)을 흉내 내는 모의 서버. 상태는 메모리에만 두고 시험마다 되돌린다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';

type ErrorCode = Schemas['ErrorCode'];
type Authority = Schemas['AdminAuthority'];
type AdminBrief = Schemas['AdminBrief'];

interface DemoAdmin extends AdminBrief {
  password: string;
  roleNames: string[];
  scopeLabel: string;
  authorities: Authority[];
}

const PASSWORD = 'Demo-admin-2026';

/** 시험·시연용 가상 계정. 화면 어디에도 노출하지 않는다. 역할 템플릿은 TDD 4.2를 따른다. */
export const DEMO_ADMINS = {
  group: {
    adminId: '2000000000000000000001',
    name: '김관리',
    loginId: 'demo-admin',
    password: PASSWORD,
    roleNames: ['운영묶음 관리자'],
    scopeLabel: '조리읍 운영묶음',
    authorities: [
      'AU.GRP_R', 'AU.CONF_W', 'AU.MBR_R', 'AU.INSTR_W', 'AU.CORS_R', 'AU.CORS_W', 'AU.APLY_R', 'AU.APLY_W',
      'AU.STLM_R', 'AU.STLM_W', 'AU.RFND_A', 'AU.RFND_X', 'AU.BBS_W', 'AU.POST_W', 'AU.SITE_W', 'AU.FCLT_W',
      'AU.GRANT_W', 'AU.LOG_R', 'AU.SMS_SEND', 'AU.STAT_R', 'AU.ATND_R',
    ],
  },
  course: {
    adminId: '2000000000000000000002',
    name: '이강좌',
    loginId: 'demo-course',
    password: PASSWORD,
    roleNames: ['강좌 담당자'],
    scopeLabel: '조리읍 운영묶음',
    authorities: ['AU.CORS_R', 'AU.CORS_W', 'AU.APLY_R', 'AU.APLY_W', 'AU.ATND_R', 'AU.STAT_R'],
  },
  finance: {
    adminId: '2000000000000000000003',
    name: '박정산',
    loginId: 'demo-finance',
    password: PASSWORD,
    roleNames: ['결제·환불 담당자'],
    scopeLabel: '조리읍 운영묶음',
    authorities: ['AU.APLY_R', 'AU.STLM_R', 'AU.STLM_W', 'AU.RFND_A', 'AU.STAT_R'],
  },
} satisfies Record<string, DemoAdmin>;

const ADMINS: DemoAdmin[] = Object.values(DEMO_ADMINS);

interface MenuDef {
  key: string;
  label: string;
  path: string;
  /** 하나라도 있으면 메뉴에 보인다. */
  anyOf: Authority[];
}

// 화면설계서 3.2의 권한 열과 TDD 9.3 경로를 따른다. 권한 코드가 '확인 필요(Q21)'인 화면은 만들 때 더한다.
const MENU: Array<{ key: string; title: string; items: MenuDef[] }> = [
  {
    key: 'status',
    title: '운영 현황',
    items: [
      { key: 'dashboard', label: '대시보드', path: '/dashboard', anyOf: ['AU.STAT_R'] },
      { key: 'stats', label: '수요·연령·정산 통계', path: '/stats', anyOf: ['AU.STAT_R'] },
    ],
  },
  {
    key: 'edu',
    title: '교육 운영',
    items: [
      { key: 'courses', label: '강좌 관리', path: '/edu/courses', anyOf: ['AU.CORS_R', 'AU.CORS_W'] },
      { key: 'cycles', label: '교육기수', path: '/edu/cycles', anyOf: ['AU.CONF_W'] },
      { key: 'schedules', label: '일정·휴보강', path: '/edu/schedules', anyOf: ['AU.CORS_W'] },
      { key: 'instructors', label: '강사 심사', path: '/edu/instructors', anyOf: ['AU.INSTR_W'] },
      { key: 'facilities', label: '센터·강의실', path: '/edu/facilities', anyOf: ['AU.FCLT_W'] },
      { key: 'attendance', label: '출석 현황', path: '/edu/attendance', anyOf: ['AU.ATND_R'] },
    ],
  },
  {
    key: 'pay',
    title: '수강·정산',
    items: [
      { key: 'applications', label: '수강신청', path: '/pay/applications', anyOf: ['AU.APLY_R'] },
      { key: 'waitlist', label: '대기·자리 배정', path: '/pay/waitlist', anyOf: ['AU.APLY_R'] },
      { key: 'transactions', label: '결제·거래 대조', path: '/pay/transactions', anyOf: ['AU.STLM_R', 'AU.STLM_W'] },
      { key: 'refunds', label: '환불 검토', path: '/pay/refunds', anyOf: ['AU.RFND_A', 'AU.RFND_X'] },
    ],
  },
  {
    key: 'member',
    title: '회원·콘텐츠',
    items: [
      { key: 'members', label: '회원 관리', path: '/mbr/members', anyOf: ['AU.MBR_R'] },
      { key: 'posts', label: '게시물·게시판', path: '/mbr/posts', anyOf: ['AU.POST_W', 'AU.BBS_W'] },
      { key: 'inquiries', label: '문의·답변', path: '/mbr/inquiries', anyOf: ['AU.POST_W'] },
      { key: 'contents', label: '홈·센터 콘텐츠', path: '/mbr/contents', anyOf: ['AU.SITE_W'] },
      { key: 'terms', label: '약관·동의문', path: '/mbr/terms', anyOf: ['AU.SITE_W'] },
      { key: 'files', label: '첨부파일', path: '/mbr/files', anyOf: ['AU.POST_W', 'AU.SITE_W'] },
    ],
  },
  {
    key: 'system',
    title: '시스템',
    items: [
      { key: 'sms', label: '알림 이력', path: '/sys/sms', anyOf: ['AU.SMS_SEND'] },
      { key: 'roles', label: '권한 배정', path: '/sys/roles', anyOf: ['AU.GRANT_W'] },
    ],
  },
];

/** 이 권한으로 보이는 메뉴. 보이는 항목이 없는 묶음은 뺀다. */
export function menuFor(authorities: readonly Authority[]): Schemas['MenuGroup'][] {
  return MENU.map((group) => ({
    key: group.key,
    title: group.title,
    items: group.items
      .filter((item) => item.anyOf.some((code) => authorities.includes(code)))
      .map(({ key, label, path }) => ({ key, label, path })),
  })).filter((group) => group.items.length > 0);
}

// 시안 값이며 승인된 관리자 정책이 아니다(PRD Q28).
const LOGIN_FAILURE_LIMIT = 5;
const DEFAULT_IDLE_SECONDS = 900;
const IDLE_KEY = 'mockIdle';

let idleOverride: number | null = null;

/** 시험에서 유휴 만료 시간을 줄인다. null이면 해제한다. */
export function setMockIdleSeconds(value: number | null): void {
  idleOverride = value;
}

function idleSeconds(): number {
  if (idleOverride !== null) return idleOverride;
  try {
    const stored = Number(window.sessionStorage.getItem(IDLE_KEY));
    return Number.isInteger(stored) && stored > 0 ? stored : DEFAULT_IDLE_SECONDS;
  } catch {
    return DEFAULT_IDLE_SECONDS;
  }
}

/**
 * 주소의 ?mockIdle=130 을 읽어 세션에 기억한다. 만료 안내와 만료 흐름을 짧은 시간에 시연하는 용도다.
 * 빈 값(?mockIdle=)이면 해제한다. 개발 서버에서만 호출되며 운영 빌드에는 들어가지 않는다.
 */
export function initMockIdleFromLocation(): void {
  try {
    const param = new URLSearchParams(window.location.search).get('mockIdle');
    if (param === null) return;
    if (param === '') window.sessionStorage.removeItem(IDLE_KEY);
    else if (Number.isInteger(Number(param)) && Number(param) > 0) window.sessionStorage.setItem(IDLE_KEY, param);
  } catch {
    // 저장소를 쓸 수 없으면 기본 시간을 쓴다.
  }
}

interface MockState {
  csrfSeq: number;
  admin: DemoAdmin | null;
  expiresAt: number;
  loginFailures: Map<string, number>;
}

const initialState = (): MockState => ({ csrfSeq: 1, admin: null, expiresAt: 0, loginFailures: new Map() });

let state = initialState();

/** 시험 사이에 세션과 로그인 실패 횟수를 처음으로 되돌린다. */
export function resetMockAuth(): void {
  state = initialState();
  idleOverride = null;
}

const MESSAGES: Partial<Record<ErrorCode, string>> = {
  CONFLICT_STATE: '현재 상태에서는 처리할 수 없습니다.',
  FORBIDDEN: '요청을 확인할 수 없습니다. 화면을 새로 열고 다시 시도해 주세요.',
  IDEMPOTENCY_CONFLICT: '같은 요청 키로 다른 내용이 전달되었습니다.',
  NOT_FOUND: '요청한 정보를 찾을 수 없습니다.',
  RFND_LIMIT_EXCEEDED: '환불 가능 금액을 초과합니다.',
  RULE_REJECTED: '처리할 수 없는 요청입니다.',
  VERSION_CONFLICT: '다른 곳에서 먼저 수정되었습니다. 새로 고친 뒤 다시 시도해 주세요.',
  LOGIN_FAILED: '아이디 또는 비밀번호를 확인해 주세요.',
  LOGIN_LOCKED: '로그인 시도가 많아 잠시 이용할 수 없습니다.',
  UNAUTHENTICATED: '로그인이 필요합니다.',
  VALIDATION_FAILED: '입력 형식이 올바르지 않습니다.',
};
const STATUS: Partial<Record<ErrorCode, number>> = {
  CONFLICT_STATE: 409,
  FORBIDDEN: 403,
  IDEMPOTENCY_CONFLICT: 409,
  NOT_FOUND: 404,
  RFND_LIMIT_EXCEEDED: 422,
  RULE_REJECTED: 422,
  VERSION_CONFLICT: 409,
  LOGIN_FAILED: 401,
  LOGIN_LOCKED: 429,
  UNAUTHENTICATED: 401,
  VALIDATION_FAILED: 400,
};

export function apiError(code: ErrorCode, fields?: Record<string, string>) {
  return HttpResponse.json(
    { code, message: MESSAGES[code] ?? code, fields: fields ?? null, requestId: `mock-${code.toLowerCase()}-0001` },
    { status: STATUS[code] ?? 400 },
  );
}

const csrfToken = () => `mock-admin-csrf-${state.csrfSeq}`;
const csrfRejected = (request: Request) => request.headers.get('X-CSRF-Token') !== csrfToken();

/** 유휴 시간이 지난 세션은 로그인하지 않은 것으로 본다. */
function currentAdmin(): DemoAdmin | null {
  if (state.admin && Date.now() >= state.expiresAt) state.admin = null;
  return state.admin;
}

function touch(): void {
  state.expiresAt = Date.now() + idleSeconds() * 1000;
}

function sessionBody(): Schemas['AdminSession'] {
  const admin = currentAdmin();
  return {
    authenticated: admin !== null,
    csrfToken: csrfToken(),
    admin: admin ? { adminId: admin.adminId, name: admin.name, loginId: admin.loginId } : null,
    idleTimeoutSeconds: admin ? idleSeconds() : null,
    expiresAt: admin ? new Date(state.expiresAt).toISOString() : null,
    serverNow: new Date().toISOString(),
  };
}

/** 지금 로그인한 모의 관리자가 가진 권한. 로그인하지 않았거나 만료되었으면 빈 배열이다. */
export const currentAuthorities = (): readonly Authority[] => currentAdmin()?.authorities ?? [];

/** 지금 로그인한 모의 관리자의 번호. 승인자와 집행자가 같은지 가릴 때 쓴다. */
export const currentAdminId = (): string => currentAdmin()?.adminId ?? '';

/** 지금 로그인한 모의 관리자의 이름. 처리 이력의 처리자에 쓴다. */
export const currentAdminName = (): string => currentAdmin()?.name ?? '';

/** 요청한 권한 중 하나라도 있으면 null, 로그인하지 않았으면 401, 권한이 없으면 403 응답을 돌려준다. */
export function denyUnless(...anyOf: Authority[]) {
  if (!currentAdmin()) return apiError('UNAUTHENTICATED');
  return anyOf.some((code) => currentAuthorities().includes(code)) ? null : apiError('FORBIDDEN');
}

/** 상태를 바꾸는 요청의 CSRF 검사. 맞지 않으면 403 응답을 돌려준다. */
export const denyCsrf = (request: Request) => (csrfRejected(request) ? apiError('FORBIDDEN') : null);

export const authHandlers = [
  http.get('/api/admin/v1/auth/session', () => HttpResponse.json(sessionBody())),

  http.post('/api/admin/v1/auth/login', async ({ request }) => {
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    const { loginId, password } = (await request.json()) as Schemas['AdminLoginRequest'];
    const failures = state.loginFailures.get(loginId) ?? 0;
    if (failures >= LOGIN_FAILURE_LIMIT) return apiError('LOGIN_LOCKED');
    const admin = ADMINS.find((item) => item.loginId === loginId);
    if (!admin || admin.password !== password) {
      state.loginFailures.set(loginId, failures + 1);
      return apiError('LOGIN_FAILED');
    }
    state.loginFailures.delete(loginId);
    state.admin = admin;
    state.csrfSeq += 1;
    touch();
    return HttpResponse.json(sessionBody());
  }),

  http.post('/api/admin/v1/auth/logout', ({ request }) => {
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    state.admin = null;
    state.csrfSeq += 1;
    return new HttpResponse(null, { status: 204 });
  }),

  http.post('/api/admin/v1/auth/extend', ({ request }) => {
    if (csrfRejected(request)) return apiError('FORBIDDEN');
    if (!currentAdmin()) return apiError('UNAUTHENTICATED');
    touch();
    return HttpResponse.json(sessionBody());
  }),

  http.get('/api/admin/v1/me/permissions', () => {
    const admin = currentAdmin();
    if (!admin) return apiError('UNAUTHENTICATED');
    return HttpResponse.json({
      roleNames: admin.roleNames,
      scopeLabel: admin.scopeLabel,
      authorities: admin.authorities,
      menu: menuFor(admin.authorities),
    } satisfies Schemas['AdminPermissions']);
  }),
];