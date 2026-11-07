// 관리자 운영 설정(읽기 전용)과 공통 코드를 흉내 내는 모의 서버. 코드는 표시명·순서·사용 여부만 바뀌고 한 번에 모두 저장되거나 하나도 저장되지 않는다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, denyCsrf, denyUnless } from './auth';

type Row = Schemas['CodeRow'];
type Setting = Schemas['SettingDetail'];

const sid = (n: number) => `90${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;

const SETTINGS: Setting[] = [
  { settingId: sid(1), name: '결제 기한', value: '600초', status: 'DECIDED', updatedOn: '2026-10-27', body: '신청 자리 배정 시각부터 600초 안에 결제해야 합니다. 결제 요청·승인 API가 기한을 다시 검사하며 워커가 늦게 돌아도 기한은 늘어나지 않습니다.', version: 2 },
  { settingId: sid(2), name: '환불 당월분 공식', value: '당월 사용분 일할 공제(안)', status: 'REVIEW', updatedOn: '2026-10-29', body: '환불 금액에서 당월 사용분을 어떻게 공제할지 기관과 협의 중입니다. 확정되기 전에는 화면과 서버에 적용하지 않습니다.', version: 1 },
  { settingId: sid(3), name: '결제 대행사(PG)', value: 'TBD', status: 'HOLD', updatedOn: '2026-10-23', body: '계약 후 정해집니다. 정해지기 전에는 값을 가정하지 않습니다.', version: 1 },
  { settingId: sid(4), name: '문자 발송 공급자', value: 'TBD (후보: NHN Cloud SMS, 알리고, 솔라피)', status: 'HOLD', updatedOn: '2026-10-23', body: '발송업체·발신번호·요금은 계약 후 정해집니다(PRD Q2).', version: 1 },
  { settingId: sid(5), name: '감면율', value: '50%', status: 'DECIDED', updatedOn: '2026-10-27', body: '조리읍 거주가 확인된 감면 대상 3종은 기수당 1강좌에 50%를 감면합니다.', version: 1 },
];

const row = (code: string, name: string, sortSeq: number, refCount: number | null, use = true): Row => ({ code, name, sortSeq, use, refCount });
function initialCodes(): Record<string, Row[]> {
  return {
    ES: [row('ES.WAIT', '대기', 10, 312), row('ES.HOLD', '결제대기', 20, 41), row('ES.CONFIRM', '수강확정', 30, 1204), row('ES.CANCEL', '취소', 40, 87), row('ES.EXPIRE', '기한만료', 50, 23), row('ES.COMPLETE', '수강종료', 60, 0)],
    FS: [row('FS.PENDING', '검사대기', 10, 3), row('FS.SAFE', '검사통과', 20, 58), row('FS.BLOCK', '차단', 30, 1), row('FS.DELETE', '삭제', 40, null)],
    DS: [row('DS.RECEIVED', '접수', 10, 2), row('DS.APPROVED', '승인', 20, 1), row('DS.REJECTED', '반려', 30, 1), row('DS.REVOKED', '철회', 40, 0, false)],
    OR: [row('OR.REVIEW', '검토중', 10, 2), row('OR.DECIDED', '확정', 20, 2), row('OR.HOLD', '보류', 30, 2)],
  };
}
const GROUPS: Schemas['CodeGroup'][] = [
  { id: 'ES', name: '수강신청상태' },
  { id: 'FS', name: '파일처리상태' },
  { id: 'DS', name: '감면사전심사상태' },
  { id: 'OR', name: '운영기준검토상태' },
];

let codes = initialCodes();

/** 시험 사이에 공통 코드를 처음 상태로 되돌린다. */
export function resetMockSettings(): void {
  codes = initialCodes();
}

const sorted = (rows: Row[]) => [...rows].sort((a, b) => a.sortSeq - b.sortSeq || a.code.localeCompare(b.code));

export const settingHandlers = [
  http.get('/api/admin/v1/settings', ({ request }) => {
    const denied = denyUnless('AU.SITE_W');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const status = params.get('status');
    const q = params.get('q')?.trim();
    const items = SETTINGS.filter((item) => (!status || item.status === status) && (!q || item.name.includes(q)));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    const summaries = items.slice((page - 1) * size, page * size).map(({ settingId, name, value, status: itemStatus, updatedOn }) => ({ settingId, name, value, status: itemStatus, updatedOn }));
    return HttpResponse.json({ items: summaries, page, size, total: items.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.get('/api/admin/v1/settings/:settingId', ({ params }) => {
    const denied = denyUnless('AU.SITE_W');
    if (denied) return denied;
    const found = SETTINGS.find((item) => item.settingId === params.settingId);
    return found ? HttpResponse.json(found) : apiError('NOT_FOUND');
  }),

  http.get('/api/admin/v1/code-groups', () => {
    const denied = denyUnless('AU.GRANT_W');
    if (denied) return denied;
    return HttpResponse.json({ items: GROUPS });
  }),

  http.get('/api/admin/v1/codes', ({ request }) => {
    const denied = denyUnless('AU.GRANT_W');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const group = GROUPS.find((item) => item.id === params.get('group'));
    if (!group) return apiError('NOT_FOUND');
    const q = params.get('q')?.trim();
    const use = params.get('use');
    const items = sorted(codes[group.id]!).filter((item) => (!q || item.code.includes(q) || item.name.includes(q)) && (use === null || item.use === (use === 'true')));
    return HttpResponse.json({ group, items } satisfies Schemas['CodeList']);
  }),

  http.put('/api/admin/v1/codes', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.GRANT_W');
    if (denied) return denied;
    const body = (await request.json()) as Schemas['CodeUpdate'];
    const group = GROUPS.find((item) => item.id === body.groupId);
    if (!group) return apiError('NOT_FOUND');
    const current = codes[group.id]!;
    const fields: Record<string, string> = {};
    for (const item of body.items) {
      if (!current.some((existing) => existing.code === item.code)) return apiError('NOT_FOUND');
      if (!item.name.trim()) fields[`${item.code}.name`] = '표시명을 입력해 주세요.';
      if (!Number.isInteger(item.sortSeq) || item.sortSeq < 0) fields[`${item.code}.sortSeq`] = '0 이상의 정수를 입력해 주세요.';
    }
    if (Object.keys(fields).length > 0) return apiError('RULE_REJECTED', fields);
    for (const item of body.items) Object.assign(current.find((existing) => existing.code === item.code)!, { name: item.name.trim(), sortSeq: item.sortSeq, use: item.use });
    return HttpResponse.json({ group, items: sorted(current) } satisfies Schemas['CodeList']);
  }),
];