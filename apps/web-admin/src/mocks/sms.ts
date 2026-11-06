// 관리자 알림 이력·문자 발송을 흉내 내는 모의 서버. 수신 대상 산정과 중복 제거는 서버가 하고 번호와 이름은 가려서 준다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, denyCsrf, denyUnless } from './auth';
import { mockCourseIds, mockCourseName } from './education';

type Detail = Schemas['SmsRequestDetail'];
type Audience = Schemas['SmsAudience'];
type TargetState = Schemas['SmsTargetState'];

const sid = (n: number) => `19${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;
const MAX_BYTES = 90;
const SURNAMES = ['김', '이', '박', '최', '정', '강', '조', '윤'];

interface State {
  rows: Detail[];
  seq: number;
  idempotent: Map<string, { fingerprint: string; body: Detail }>;
}

const targetRows = (count: number, states: TargetState[]): Detail['targets'] =>
  Array.from({ length: Math.min(count, 200) }, (_, index) => {
    const state = states[index % states.length]!;
    return {
      targetId: `2${String(index + 1).padStart(21, '0')}`,
      name: `${SURNAMES[index % SURNAMES.length]}○○`,
      phone: `010-****-${String(1000 + index).slice(-4)}`,
      state,
      attempts: state === 'WAIT' ? 0 : 1,
      failCode: state === 'FAIL' ? 'NO_ROUTE' : null,
      failReason: state === 'FAIL' ? '수신번호 사용 불가' : null,
    };
  });

function row(n: number, kind: Schemas['SmsKind'], scope: Schemas['SmsScope'], content: string, at: string, by: string, states: TargetState[], count: number, courseNames: string[] = []): Detail {
  const targets = targetRows(count, states);
  const tally = (state: TargetState) => targets.filter((target) => target.state === state).length;
  return {
    smsId: sid(n), requestedAt: at, kind, scope, summary: content.slice(0, 24), targetCount: count, sent: tally('SENT'), failed: tally('FAIL'), unknown: tally('UNKNOWN'), requestedBy: by,
    content, courseNames, targets, targetsTruncated: count > 200,
  };
}

function initialState(): State {
  const rows: Detail[] = [
    row(1, 'AUTO', 'EVENT', '[조리읍 주민자치센터] 건강요가 초급 자리가 배정되었습니다. 10분 안에 결제해 주세요.', '2026-10-30T14:18:00+09:00', 'SYSTEM', ['SENT'], 1),
    row(2, 'AUTO', 'EVENT', '[조리읍 주민자치센터] 결제 기한 안내', '2026-10-29T09:00:00+09:00', 'SYSTEM', ['SENT', 'SENT', 'SENT', 'FAIL', 'UNKNOWN'], 5),
    row(3, 'MANUAL', 'COURSE', '11월 11일은 휴강입니다.', '2026-10-28T16:30:00+09:00', '김관리', [...Array<TargetState>(3).fill('FAIL'), 'UNKNOWN', ...Array<TargetState>(29).fill('SENT')], 33, ['건강요가 초급', '스마트폰 기초']),
  ];
  return { rows, seq: 20, idempotent: new Map() };
}

let state = initialState();

/** 시험 사이에 문자 이력을 처음 상태로 되돌린다. */
export function resetMockSms(): void {
  state = initialState();
}

const bytesOf = (text: string) => [...text].reduce((sum, char) => sum + (char.codePointAt(0)! > 127 ? 2 : 1), 0);
const summary = (detail: Detail): Schemas['SmsRequestSummary'] => ({ smsId: detail.smsId, requestedAt: detail.requestedAt, kind: detail.kind, scope: detail.scope, summary: detail.summary, targetCount: detail.targetCount, sent: detail.sent, failed: detail.failed, unknown: detail.unknown, requestedBy: detail.requestedBy });

// 강좌마다 상태별 인원이 정해져 있다고 가정한다. 센터 전체는 모든 강좌를 더한다.
const headcount = (courseId: string, status: Schemas['SmsAudienceStatus']): number => {
  const n = Number(courseId.slice(-3)) || 0;
  return status === 'CONFIRMED' ? 10 + n : status === 'PAYMENT_PENDING' ? n % 3 : n % 4;
};

function audience(body: Audience): { fields: Record<string, string> } | { total: number; duplicate: number; courseIds: string[] } {
  const fields: Record<string, string> = {};
  if (body.scope === 'EVENT') fields.scope = '센터 전체나 선택 강좌만 고를 수 있습니다.';
  const selected = body.courseIds ?? [];
  if (body.scope === 'COURSE' && selected.length === 0) fields.courseIds = '강좌를 하나 이상 선택해 주세요.';
  if (!body.content.trim()) fields.content = '문안을 입력해 주세요.';
  else if (bytesOf(body.content) > MAX_BYTES) fields.content = `${MAX_BYTES}바이트(한글 45자)를 넘을 수 없습니다.`;
  if (Object.keys(fields).length > 0) return { fields };
  const courseIds = body.scope === 'CENTER' ? mockCourseIds() : selected;
  const total = courseIds.reduce((sum, courseId) => sum + body.statuses.reduce((inner, status) => inner + headcount(courseId, status), 0), 0);
  const duplicate = courseIds.length > 1 ? Math.min(3, total) : 0;
  return { total: total - duplicate, duplicate, courseIds };
}

export const smsHandlers = [
  http.get('/api/admin/v1/sms', ({ request }) => {
    const denied = denyUnless('AU.SMS_SEND');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const kind = params.get('kind') ?? 'AUTO';
    const rows = state.rows.filter((item) => item.kind === kind).sort((a, b) => b.requestedAt.localeCompare(a.requestedAt));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size).map(summary), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.get('/api/admin/v1/sms/:smsId', ({ params }) => {
    const denied = denyUnless('AU.SMS_SEND');
    if (denied) return denied;
    const found = state.rows.find((item) => item.smsId === params.smsId);
    return found ? HttpResponse.json(found) : apiError('NOT_FOUND');
  }),

  http.post('/api/admin/v1/sms/preview', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.SMS_SEND');
    if (denied) return denied;
    const body = (await request.json()) as Audience;
    const result = audience(body);
    if ('fields' in result) return apiError('RULE_REJECTED', result.fields);
    const recipients = Array.from({ length: Math.min(result.total, 50) }, (_, index) => ({ name: `${SURNAMES[index % SURNAMES.length]}○○`, phone: `010-****-${String(1000 + index).slice(-4)}` }));
    return HttpResponse.json({ recipientCount: result.total, duplicateRemoved: result.duplicate, courseCount: result.courseIds.length, centerName: '조리읍', byteLength: bytesOf(body.content), recipients } satisfies Schemas['SmsPreview']);
  }),

  http.post('/api/admin/v1/sms', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.SMS_SEND');
    if (denied) return denied;
    const body = (await request.json()) as Schemas['SmsSendRequest'];
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(found.body, { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
    if (!body.confirmed) return apiError('RULE_REJECTED', { confirmed: '수신 대상과 문안을 최종 확인해 주세요.' });
    const result = audience(body);
    if ('fields' in result) return apiError('RULE_REJECTED', result.fields);
    if (result.total !== body.expectedRecipientCount) return apiError('CONFLICT_STATE', { expectedRecipientCount: `수신 대상이 바뀌었습니다. 현재 ${result.total}명입니다.` });
    state.seq += 1;
    const created = row(state.seq, 'MANUAL', body.scope, body.content, new Date().toISOString(), currentAdminName(), ['WAIT'], result.total, result.courseIds.map(mockCourseName).filter(Boolean));
    state.rows.push(created);
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: created });
    return HttpResponse.json(created, { status: 201 });
  }),
];