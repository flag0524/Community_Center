// 관리자 권한 배정을 흉내 내는 모의 서버. 위임 가능 여부와 상태는 서버가 정하고 자기 자신에게는 줄 수 없다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminId, currentAdminName, currentAuthorities, DEMO_ADMINS, denyCsrf, denyUnless } from './auth';

type Authority = Schemas['AdminAuthority'];
type Scope = Schemas['AssignmentScope'];

const PAGE_SIZE = 20;
const aid = (n: number) => `70${String(n).padStart(20, '0')}`;
const rid = (n: number) => `71${String(n).padStart(20, '0')}`;
const DONG = { id: '7200000000000000000001', name: '조리읍' };
const OTHER_ADMIN = { id: '2000000000000000000004', name: '최담당' };
const ADMIN_NAMES: Record<string, string> = { [DEMO_ADMINS.group.adminId]: '김관리', [DEMO_ADMINS.course.adminId]: '이강좌', [DEMO_ADMINS.finance.adminId]: '박정산', [OTHER_ADMIN.id]: OTHER_ADMIN.name };

const ROLES: Array<Schemas['AssignmentRoleOption']> = [
  { id: rid(1), name: '전체 운영구조 관리자', scopes: ['SYSTEM'], authorities: ['AU.GRP_R', 'AU.GRP_W', 'AU.DONG_W', 'AU.MNGR_W', 'AU.ROLE_W', 'AU.GRANT_W'] },
  { id: rid(2), name: '운영묶음 관리자', scopes: ['GROUP'], authorities: ['AU.CONF_W', 'AU.MBR_R', 'AU.INSTR_W', 'AU.CORS_R', 'AU.CORS_W', 'AU.APLY_R', 'AU.APLY_W', 'AU.STLM_R', 'AU.STLM_W', 'AU.RFND_A', 'AU.RFND_X', 'AU.BBS_W', 'AU.POST_W', 'AU.SITE_W', 'AU.FCLT_W', 'AU.GRANT_W', 'AU.LOG_R', 'AU.SMS_SEND', 'AU.STAT_R', 'AU.ATND_R'] },
  { id: rid(3), name: '동 담당자', scopes: ['DONG'], authorities: ['AU.MBR_R', 'AU.CORS_R', 'AU.CORS_W', 'AU.APLY_R', 'AU.APLY_W', 'AU.STLM_R', 'AU.POST_W', 'AU.SITE_W', 'AU.FCLT_W'] },
  { id: rid(4), name: '강좌 담당자', scopes: ['GROUP', 'DONG'], authorities: ['AU.CORS_R', 'AU.CORS_W', 'AU.APLY_R', 'AU.APLY_W'] },
  { id: rid(5), name: '콘텐츠 담당자', scopes: ['GROUP', 'DONG'], authorities: ['AU.POST_W', 'AU.SITE_W'] },
  { id: rid(6), name: '결제·환불 담당자', scopes: ['GROUP', 'DONG'], authorities: ['AU.STLM_R', 'AU.STLM_W', 'AU.RFND_A', 'AU.RFND_X'] },
];

interface Row {
  assignmentId: string;
  adminId: string;
  roleId: string;
  scope: Scope;
  dongId: string | null;
  validFrom: string;
  validTo: string | null;
  grantedBy: string;
  grantedAt: string;
  revoked: boolean;
  version: number;
}
interface State {
  rows: Row[];
  seq: number;
  idempotent: Map<string, { fingerprint: string; body: Schemas['RoleAssignment'] }>;
}

function initialState(): State {
  const row = (n: number, adminId: string, roleNo: number, scope: Scope, validFrom: string, validTo: string | null, grantedBy: string): Row => ({
    assignmentId: aid(n), adminId, roleId: rid(roleNo), scope, dongId: scope === 'DONG' ? DONG.id : null, validFrom, validTo, grantedBy, grantedAt: `${validFrom}T09:00:00+09:00`, revoked: false, version: 1,
  });
  return {
    rows: [
      row(1, DEMO_ADMINS.group.adminId, 2, 'GROUP', '2026-01-01', null, '구조관리자'),
      row(2, DEMO_ADMINS.course.adminId, 4, 'GROUP', '2026-03-01', '2030-12-31', '김관리'),
      row(3, DEMO_ADMINS.finance.adminId, 6, 'GROUP', '2026-03-01', null, '김관리'),
      row(4, DEMO_ADMINS.course.adminId, 5, 'DONG', '2025-01-01', '2025-12-31', '김관리'),
      row(5, DEMO_ADMINS.finance.adminId, 3, 'DONG', '2027-01-01', '2027-12-31', '김관리'),
    ],
    seq: 20,
    idempotent: new Map(),
  };
}

let state = initialState();

/** 시험 사이에 권한 배정을 처음 상태로 되돌린다. */
export function resetMockRoles(): void {
  state = initialState();
}

const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
const roleOf = (roleId: string) => ROLES.find((role) => role.id === roleId)!;
const statusOf = (row: Row): Schemas['AssignmentStatus'] => (row.revoked ? 'REVOKED' : row.validTo && row.validTo < today() ? 'EXPIRED' : row.validFrom > today() ? 'SCHEDULED' : 'ACTIVE');
const scopeLabel = (row: Row) => (row.scope === 'SYSTEM' ? '전체 운영구조' : row.scope === 'GROUP' ? '조리읍 묶음 전체' : DONG.name);
const summary = (row: Row): Schemas['RoleAssignmentSummary'] => ({ assignmentId: row.assignmentId, adminName: ADMIN_NAMES[row.adminId] ?? '', roleName: roleOf(row.roleId).name, scope: row.scope, scopeLabel: scopeLabel(row), validFrom: row.validFrom, validTo: row.validTo, status: statusOf(row), grantedBy: row.grantedBy });
const detail = (row: Row): Schemas['RoleAssignment'] => ({ ...summary(row), authorities: roleOf(row.roleId).authorities, grantedAt: row.grantedAt, version: row.version, canRevoke: ['ACTIVE', 'SCHEDULED'].includes(statusOf(row)) && row.adminId !== currentAdminId() });
// 내가 가진 권한 안에 드는 역할만 위임할 수 있다.
const delegable = () => ROLES.filter((role) => role.authorities.every((authority) => currentAuthorities().includes(authority as Authority)));
const PRIORITY: Record<string, number> = { ACTIVE: 0, SCHEDULED: 1, EXPIRED: 2, REVOKED: 3 };

export const roleHandlers = [
  http.get('/api/admin/v1/role-assignment-options', () => {
    const denied = denyUnless('AU.GRANT_W');
    if (denied) return denied;
    const admins = [...Object.values(ADMIN_NAMES).map((name, index) => ({ id: Object.keys(ADMIN_NAMES)[index]!, name }))].filter((item) => item.id !== currentAdminId());
    return HttpResponse.json({ admins, roles: delegable(), dongs: [DONG] } satisfies Schemas['AssignmentOptions']);
  }),

  http.get('/api/admin/v1/role-assignments', ({ request }) => {
    const denied = denyUnless('AU.GRANT_W');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const status = params.get('status');
    const q = params.get('q')?.trim();
    const rows = state.rows
      .filter((row) => (!status || statusOf(row) === status) && (!q || (ADMIN_NAMES[row.adminId] ?? '').includes(q)))
      .sort((a, b) => PRIORITY[statusOf(a)]! - PRIORITY[statusOf(b)]! || b.validFrom.localeCompare(a.validFrom) || b.assignmentId.localeCompare(a.assignmentId));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size).map(summary), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null }, canGrant: true });
  }),

  http.get('/api/admin/v1/role-assignments/:assignmentId', ({ params }) => {
    const denied = denyUnless('AU.GRANT_W');
    if (denied) return denied;
    const row = state.rows.find((item) => item.assignmentId === params.assignmentId);
    return row ? HttpResponse.json(detail(row)) : apiError('NOT_FOUND');
  }),

  http.post('/api/admin/v1/role-assignments', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.GRANT_W');
    if (denied) return denied;
    const body = (await request.json()) as Schemas['AssignmentCreate'];
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(found.body, { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
    const fields: Record<string, string> = {};
    const role = delegable().find((item) => item.id === body.roleId);
    if (body.adminId === currentAdminId()) fields.adminId = '자기 자신에게는 배정할 수 없습니다. 다른 권한 관리자에게 요청해 주세요.';
    else if (!ADMIN_NAMES[body.adminId]) fields.adminId = '관리자를 찾을 수 없습니다.';
    if (!role) fields.roleId = '위임할 수 없는 역할입니다.';
    else if (!role.scopes.includes(body.scope)) fields.scope = '이 역할에는 쓸 수 없는 범위입니다.';
    if (body.scope === 'DONG' && body.dongId !== DONG.id) fields.dongId = '동을 선택해 주세요.';
    if (body.scope !== 'DONG' && body.dongId) fields.dongId = '동은 동 범위에서만 고릅니다.';
    if (body.validTo && body.validTo <= body.validFrom) fields.validTo = '유효 종료일은 시작일 이후여야 합니다.';
    if (!fields.roleId && !fields.adminId && state.rows.some((row) => row.adminId === body.adminId && row.roleId === body.roleId && row.scope === body.scope && row.dongId === (body.dongId ?? null) && ['ACTIVE', 'SCHEDULED'].includes(statusOf(row)))) fields.roleId = '같은 관리자에게 같은 역할·범위의 유효한 배정이 이미 있습니다.';
    if (Object.keys(fields).length > 0) return apiError('RULE_REJECTED', fields);
    state.seq += 1;
    const created: Row = { assignmentId: aid(state.seq), adminId: body.adminId, roleId: body.roleId, scope: body.scope, dongId: body.dongId ?? null, validFrom: body.validFrom, validTo: body.validTo ?? null, grantedBy: currentAdminName(), grantedAt: new Date().toISOString(), revoked: false, version: 1 };
    state.rows.push(created);
    const result = detail(created);
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: result });
    return HttpResponse.json(result, { status: 201 });
  }),

  http.post('/api/admin/v1/role-assignments/:assignmentId/revoke', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.GRANT_W');
    if (denied) return denied;
    const row = state.rows.find((item) => item.assignmentId === params.assignmentId);
    if (!row) return apiError('NOT_FOUND');
    const { version } = (await request.json()) as Schemas['AssignmentRevoke'];
    if (version !== row.version) return apiError('VERSION_CONFLICT');
    if (row.adminId === currentAdminId()) return apiError('RULE_REJECTED', { assignmentId: '자기 자신의 배정은 직접 회수할 수 없습니다.' });
    if (!['ACTIVE', 'SCHEDULED'].includes(statusOf(row))) return apiError('CONFLICT_STATE');
    Object.assign(row, { revoked: true, version: row.version + 1 });
    return HttpResponse.json(detail(row));
  }),
];