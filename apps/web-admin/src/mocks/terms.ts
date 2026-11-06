// 관리자 약관·동의문 버전을 흉내 내는 모의 서버. 검토→확정→게시 순서와 문안 해시 고정은 서버가 정하는 대로 따른다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, denyCsrf, denyUnless } from './auth';

type Version = Schemas['TermVersion'];
type TermType = Schemas['TermType'];

const tid = (n: number) => `30${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;
const TYPES: TermType[] = ['TERMS_OF_USE', 'PRIVACY_CONSENT', 'MARKETING_CONSENT', 'PRIVACY_POLICY', 'EMAIL_REFUSAL'];

interface State {
  rows: Version[];
  seq: number;
  idempotent: Map<string, { fingerprint: string; body: Version }>;
}

// 시험용 가짜 해시다. 같은 문안이면 같은 값이 나오면 충분하다.
function fakeHash(text: string): string {
  let hash = 5381;
  let out = '';
  for (let round = 0; round < 8; round += 1) {
    for (const char of `${round}${text}`) hash = (hash * 33 + char.codePointAt(0)!) >>> 0;
    out += hash.toString(16).padStart(8, '0');
  }
  return out;
}

const flags = (status: Schemas['TermStatus']) => ({ canEdit: status === 'REVIEW', canFix: status === 'REVIEW', canPublish: status === 'FIXED' });

function initialState(): State {
  const row = (n: number, termType: TermType, versionName: string, status: Schemas['TermStatus'], extra: Partial<Version> = {}): Version => ({
    versionId: tid(n),
    termType,
    versionName,
    effectiveOn: '2026-01-01',
    essential: termType !== 'MARKETING_CONSENT',
    status,
    postedOn: status === 'REVIEW' || status === 'FIXED' ? null : '2025-12-20',
    agreedCount: status === 'PUBLISHED' || status === 'ENDED' ? 1200 : 0,
    body: `${versionName} 문안입니다.\n제1조 (목적) 이 문안은 조리읍 주민자치센터 수강시스템 이용에 관한 사항을 정합니다.`,
    contentHash: null,
    version: 1,
    ...flags(status),
    ...extra,
  });
  const fixed = (version: Version): Version => ({ ...version, contentHash: fakeHash(version.body) });
  const rows: Version[] = [
    fixed(row(1, 'TERMS_OF_USE', 'v1.0', 'ENDED', { effectiveOn: '2025-03-01', agreedCount: 310, postedOn: '2025-02-20' })),
    fixed(row(2, 'TERMS_OF_USE', 'v1.1', 'PUBLISHED', { effectiveOn: '2026-01-01', agreedCount: 1204 })),
    row(3, 'TERMS_OF_USE', 'v1.2', 'REVIEW', { effectiveOn: '2027-01-01' }),
    fixed(row(4, 'PRIVACY_CONSENT', 'v1.0', 'PUBLISHED', { agreedCount: 1198 })),
    fixed(row(5, 'MARKETING_CONSENT', 'v1.0', 'PUBLISHED', { agreedCount: 402 })),
    fixed(row(6, 'PRIVACY_POLICY', 'v1.0', 'PUBLISHED', { agreedCount: 0 })),
    fixed(row(7, 'EMAIL_REFUSAL', 'v1.0', 'FIXED', { effectiveOn: '2026-12-01' })),
  ];
  return { rows, seq: 20, idempotent: new Map() };
}

let state = initialState();

/** 시험 사이에 약관을 처음 상태로 되돌린다. */
export function resetMockTerms(): void {
  state = initialState();
}

const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
const summary = (v: Version): Schemas['TermVersionSummary'] => ({ versionId: v.versionId, termType: v.termType, versionName: v.versionName, effectiveOn: v.effectiveOn, essential: v.essential, status: v.status, postedOn: v.postedOn, agreedCount: v.agreedCount });
const refresh = (v: Version) => Object.assign(v, flags(v.status), { version: v.version + 1 });

export const termHandlers = [
  http.get('/api/admin/v1/terms', ({ request }) => {
    const denied = denyUnless('AU.SITE_W');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const type = params.get('type');
    const rows = state.rows.filter((row) => !type || row.termType === type).sort((a, b) => b.effectiveOn.localeCompare(a.effectiveOn) || b.versionId.localeCompare(a.versionId));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size).map(summary), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.get('/api/admin/v1/terms/versions/:versionId', ({ params }) => {
    const denied = denyUnless('AU.SITE_W');
    if (denied) return denied;
    const row = state.rows.find((item) => item.versionId === params.versionId);
    return row ? HttpResponse.json(row) : apiError('NOT_FOUND');
  }),

  http.post('/api/admin/v1/terms/:termType/versions', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.SITE_W');
    if (denied) return denied;
    const termType = params.termType as TermType;
    if (!TYPES.includes(termType)) return apiError('NOT_FOUND');
    const body = (await request.json()) as Schemas['TermVersionCreate'];
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(found.body, { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
    const base = body.baseVersionId ? state.rows.find((row) => row.versionId === body.baseVersionId && row.termType === termType) : undefined;
    if (body.baseVersionId && !base) return apiError('NOT_FOUND');
    const text = body.body?.trim() ? body.body : (base?.body ?? '');
    const fields: Record<string, string> = {};
    if (!text.trim()) fields.body = '본문을 입력해 주세요.';
    if (state.rows.some((row) => row.termType === termType && row.versionName === body.versionName.trim())) fields.versionName = '같은 이름의 버전이 이미 있습니다.';
    if (Object.keys(fields).length > 0) return apiError('RULE_REJECTED', fields);
    state.seq += 1;
    const created: Version = { versionId: tid(state.seq), termType, versionName: body.versionName.trim(), effectiveOn: body.effectiveOn, essential: body.essential, status: 'REVIEW', postedOn: null, agreedCount: 0, body: text, contentHash: null, version: 1, ...flags('REVIEW') };
    state.rows.push(created);
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: created });
    return HttpResponse.json(created, { status: 201 });
  }),

  http.put('/api/admin/v1/terms/versions/:versionId', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.SITE_W');
    if (denied) return denied;
    const row = state.rows.find((item) => item.versionId === params.versionId);
    if (!row) return apiError('NOT_FOUND');
    const body = (await request.json()) as Schemas['TermVersionUpdate'];
    if (body.version !== row.version) return apiError('VERSION_CONFLICT');
    if (row.status !== 'REVIEW') return apiError('CONFLICT_STATE');
    if (state.rows.some((item) => item.termType === row.termType && item.versionId !== row.versionId && item.versionName === body.versionName.trim())) return apiError('RULE_REJECTED', { versionName: '같은 이름의 버전이 이미 있습니다.' });
    if (!body.body.trim()) return apiError('RULE_REJECTED', { body: '본문을 입력해 주세요.' });
    Object.assign(row, { versionName: body.versionName.trim(), effectiveOn: body.effectiveOn, essential: body.essential, body: body.body });
    refresh(row);
    return HttpResponse.json(row);
  }),

  http.post('/api/admin/v1/terms/versions/:versionId/fix', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.SITE_W');
    if (denied) return denied;
    const row = state.rows.find((item) => item.versionId === params.versionId);
    if (!row) return apiError('NOT_FOUND');
    const { version } = (await request.json()) as Schemas['TermVersionAction'];
    if (version !== row.version) return apiError('VERSION_CONFLICT');
    if (row.status !== 'REVIEW') return apiError('CONFLICT_STATE');
    Object.assign(row, { status: 'FIXED', contentHash: fakeHash(row.body) });
    refresh(row);
    return HttpResponse.json(row);
  }),

  http.post('/api/admin/v1/terms/versions/:versionId/publish', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.SITE_W');
    if (denied) return denied;
    const row = state.rows.find((item) => item.versionId === params.versionId);
    if (!row) return apiError('NOT_FOUND');
    const { version } = (await request.json()) as Schemas['TermVersionAction'];
    if (version !== row.version) return apiError('VERSION_CONFLICT');
    if (row.status !== 'FIXED') return apiError('CONFLICT_STATE');
    for (const other of state.rows) if (other.termType === row.termType && other.status === 'PUBLISHED') refresh(Object.assign(other, { status: 'ENDED' as const }));
    Object.assign(row, { status: 'PUBLISHED', postedOn: today() });
    refresh(row);
    return HttpResponse.json(row);
  }),
];