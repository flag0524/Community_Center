// 관리자 강좌분류를 흉내 내는 모의 서버. 이름은 정규화해 삭제한 분류까지 중복을 막고 연결 강좌 수를 확인하지 못하면 중지·삭제를 막는다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, currentAuthorities, denyCsrf, denyUnless } from './auth';

type Entry = Schemas['ClassHistoryEntry'];

const kid = (n: number) => `91${String(n).padStart(20, '0')}`;

interface Item {
  classId: string;
  name: string;
  sortSeq: number;
  active: boolean;
  courseCount: number | null;
  version: number;
  history: Entry[];
}
interface State {
  items: Item[];
  reservedKeys: Set<string>;
  seq: number;
  idempotent: Map<string, { fingerprint: string; body: Schemas['CourseClass'] }>;
}

// 정규화는 NFKC, 앞뒤·중복 공백 정리, 대소문자 통일이다(CLSF-01).
const normalize = (name: string) => name.normalize('NFKC').replace(/\s+/g, ' ').trim().toLowerCase();

function initialState(): State {
  const item = (n: number, name: string, sortSeq: number, courseCount: number | null, active = true): Item => ({
    classId: kid(n), name, sortSeq, active, courseCount, version: 1,
    history: [{ at: '2026-09-01T09:00:00+09:00', by: '구조관리자', action: 'CREATE', before: null, after: name }],
  });
  const items = [item(1, '컴퓨터', 10, 12), item(2, '어학/교양', 20, 8), item(3, '생활체육/건강', 30, 15), item(4, '문화/취미', 40, 0), item(5, '댄스', 50, 0, false), item(6, '공예', 60, null)];
  return { items, reservedKeys: new Set(items.map((entry) => normalize(entry.name))), seq: 20, idempotent: new Map() };
}

let state = initialState();

/** 시험 사이에 강좌분류를 처음 상태로 되돌린다. */
export function resetMockClasses(): void {
  state = initialState();
}

const present = (entry: Item): Schemas['CourseClass'] => ({
  classId: entry.classId, name: entry.name, sortSeq: entry.sortSeq, active: entry.active, courseCount: entry.courseCount, version: entry.version,
  canDeactivate: entry.active && entry.courseCount === 0,
  canDelete: entry.courseCount === 0,
});
const sorted = () => [...state.items].sort((a, b) => a.sortSeq - b.sortSeq || a.classId.localeCompare(b.classId));
const blockMessage = (entry: Item) => (entry.courseCount === null ? '연결 강좌 수를 확인하지 못해 처리할 수 없습니다.' : '연결된 강좌가 있어 처리할 수 없습니다.');
const log = (entry: Item, action: Entry['action'], before: string | null, after: string | null) => entry.history.push({ at: new Date().toISOString(), by: currentAdminName(), action, before, after });

function nameProblem(name: string, ownId?: string): string | null {
  const key = normalize(name);
  if (!key) return '분류명을 입력해 주세요.';
  if ([...key].length > 128) return '분류명은 128자를 넘을 수 없습니다.';
  const ownKey = state.items.find((entry) => entry.classId === ownId)?.name;
  if (state.reservedKeys.has(key) && (ownKey === undefined || normalize(ownKey) !== key)) return '같은 이름의 분류가 이미 있습니다. 삭제한 분류의 이름도 다시 쓸 수 없습니다.';
  return null;
}

export const classHandlers = [
  http.get('/api/admin/v1/course-classes', () => {
    const denied = denyUnless('AU.CORS_R', 'AU.CORS_W');
    if (denied) return denied;
    return HttpResponse.json({ items: sorted().map(present), canEdit: currentAuthorities().includes('AU.CORS_W'), uncategorizedCount: 2 } satisfies Schemas['CourseClassList']);
  }),

  http.post('/api/admin/v1/course-classes', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const body = (await request.json()) as Schemas['CourseClassWrite'];
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(found.body, { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
    const problem = nameProblem(body.name);
    if (problem) return apiError('RULE_REJECTED', { name: problem });
    state.seq += 1;
    const created: Item = { classId: kid(state.seq), name: body.name.normalize('NFKC').replace(/\s+/g, ' ').trim(), sortSeq: body.sortSeq, active: true, courseCount: 0, version: 1, history: [] };
    log(created, 'CREATE', null, created.name);
    state.items.push(created);
    state.reservedKeys.add(normalize(created.name));
    const result = present(created);
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: result });
    return HttpResponse.json(result, { status: 201 });
  }),

  http.put('/api/admin/v1/course-classes/:classId', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const entry = state.items.find((item) => item.classId === params.classId);
    if (!entry) return apiError('NOT_FOUND');
    const body = (await request.json()) as Schemas['CourseClassUpdate'];
    if (body.version !== entry.version) return apiError('VERSION_CONFLICT');
    const problem = nameProblem(body.name, entry.classId);
    if (problem) return apiError('RULE_REJECTED', { name: problem });
    const name = body.name.normalize('NFKC').replace(/\s+/g, ' ').trim();
    if (name !== entry.name) {
      log(entry, 'RENAME', entry.name, name);
      state.reservedKeys.add(normalize(name));
      entry.name = name;
    }
    if (body.sortSeq !== entry.sortSeq) {
      log(entry, 'REORDER', String(entry.sortSeq), String(body.sortSeq));
      entry.sortSeq = body.sortSeq;
    }
    entry.version += 1;
    return HttpResponse.json(present(entry));
  }),

  http.post('/api/admin/v1/course-classes/:classId/deactivate', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const entry = state.items.find((item) => item.classId === params.classId);
    if (!entry) return apiError('NOT_FOUND');
    const { version } = (await request.json()) as Schemas['CourseClassAction'];
    if (version !== entry.version) return apiError('VERSION_CONFLICT');
    if (!entry.active) return apiError('CONFLICT_STATE');
    if (entry.courseCount !== 0) return apiError('RULE_REJECTED', { classId: blockMessage(entry) });
    log(entry, 'DEACTIVATE', '사용', '사용 안 함');
    Object.assign(entry, { active: false, version: entry.version + 1 });
    return HttpResponse.json(present(entry));
  }),

  http.post('/api/admin/v1/course-classes/:classId/activate', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const entry = state.items.find((item) => item.classId === params.classId);
    if (!entry) return apiError('NOT_FOUND');
    const { version } = (await request.json()) as Schemas['CourseClassAction'];
    if (version !== entry.version) return apiError('VERSION_CONFLICT');
    if (entry.active) return apiError('CONFLICT_STATE');
    log(entry, 'ACTIVATE', '사용 안 함', '사용');
    Object.assign(entry, { active: true, version: entry.version + 1 });
    return HttpResponse.json(present(entry));
  }),

  http.delete('/api/admin/v1/course-classes/:classId', ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.CORS_W');
    if (denied) return denied;
    const entry = state.items.find((item) => item.classId === params.classId);
    if (!entry) return apiError('NOT_FOUND');
    if (Number(new URL(request.url).searchParams.get('version')) !== entry.version) return apiError('VERSION_CONFLICT');
    if (entry.courseCount !== 0) return apiError('RULE_REJECTED', { classId: blockMessage(entry) });
    log(entry, 'DELETE', entry.name, null);
    state.items = state.items.filter((item) => item !== entry);
    return new HttpResponse(null, { status: 204 });
  }),

  http.get('/api/admin/v1/course-classes/:classId/history', ({ params }) => {
    const denied = denyUnless('AU.CORS_R', 'AU.CORS_W');
    if (denied) return denied;
    const entry = state.items.find((item) => item.classId === params.classId);
    return entry ? HttpResponse.json({ items: [...entry.history].reverse() } satisfies Schemas['ClassHistoryList']) : apiError('NOT_FOUND');
  }),
];