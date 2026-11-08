// 개인식별 명단 암호화 내보내기를 흉내 내는 모의 서버. 요청마다 새 암호로 진짜 AES-256 ZIP을 만들고 파일과 암호를 남기지 않는다
import { Uint8ArrayReader, Uint8ArrayWriter, ZipWriter } from '@zip.js/zip.js';
import { HttpResponse, http } from 'msw';
import { applicationPiiRows } from './applications';
import { apiError, denyCsrf, denyUnless } from './auth';
import { csvText, exportLog, type Cell } from './csv';
import { memberPiiRows } from './members';

export const PII_MAX_ROWS = 5000;
const PASSWORD_LENGTH = 16;
// 헷갈리는 글자(0 O 1 l I)를 뺀 56자
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';

// 같은 멱등키로 다시 보내면 암호를 다시 줄 수 없어 거절한다. 암호는 어디에도 두지 않는다
const usedKeys = new Set<string>();
export function resetMockPii(): void {
  usedKeys.clear();
}

/** 무작위 암호. 알파벳 크기로 나누어 떨어지지 않는 바이트는 버려 한쪽으로 치우치지 않게 한다. */
export function newPassword(): string {
  const limit = 256 - (256 % ALPHABET.length);
  let text = '';
  while (text.length < PASSWORD_LENGTH) {
    for (const byte of crypto.getRandomValues(new Uint8Array(PASSWORD_LENGTH))) {
      if (byte < limit && text.length < PASSWORD_LENGTH) text += ALPHABET[byte % ALPHABET.length];
    }
  }
  return text;
}

const TARGETS = {
  MEMBERS: { authority: 'AU.MBR_R', base: 'members', header: ['아이디', '이름', '연락처', '이메일', '가입일', '상태'], rows: memberPiiRows },
  APPLICATIONS: { authority: 'AU.APLY_R', base: 'applications', header: ['신청번호', '신청자', '연락처', '강좌', '신청상태', '접수시각'], rows: applicationPiiRows },
} as const;

export async function piiZipResponse(base: string, header: string[], rows: Cell[][]) {
  if (rows.length > PII_MAX_ROWS) {
    const message = '내려받을 행이 5천 건을 넘습니다. 조건을 좁혀 주세요.';
    return HttpResponse.json({ code: 'RULE_REJECTED', message, fields: null, requestId: 'mock-pii-limit-0001' }, { status: 422 });
  }
  const password = newPassword();
  // Blob 대신 바이트 배열로 다룬다. 시험 환경(jsdom)의 Blob에는 stream()이 없다
  const writer = new ZipWriter(new Uint8ArrayWriter(), { password, encryptionStrength: 3, useWebWorkers: false });
  await writer.add(`${base}.csv`, new Uint8ArrayReader(new TextEncoder().encode(`\uFEFF${csvText(header, rows)}`)));
  const zip = await writer.close();
  // 생성 사실만 남긴다. 암호와 파일 내용은 남기지 않는다
  exportLog.push({ name: `${base}-pii.zip`, rows: rows.length });
  return new HttpResponse(zip, {
    headers: {
      'Content-Type': 'application/zip',
      'Content-Disposition': `attachment; filename="${base}-pii.zip"`,
      'X-Export-Password': password,
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'private, no-store',
    },
  });
}

interface PiiBody {
  target: keyof typeof TARGETS;
  q?: string;
  status?: string;
  cycleId?: string;
  courseId?: string;
  paymentStatus?: string;
  from?: string;
  to?: string;
}

export const piiHandlers = [
  http.post('/api/admin/v1/exports/pii', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.EXPORT');
    if (denied) return denied;
    const body = (await request.json()) as PiiBody;
    const target = TARGETS[body.target];
    if (!target) return apiError('RULE_REJECTED', { target: '내보낼 수 없는 목록입니다.' });
    // 내보내기 권한이 있어도 그 목록을 볼 수 있어야 한다
    const noAccess = denyUnless(target.authority);
    if (noAccess) return noAccess;
    const key = request.headers.get('Idempotency-Key');
    if (!key) return apiError('RULE_REJECTED', { 'Idempotency-Key': '멱등키가 필요합니다.' });
    if (usedKeys.has(key)) return apiError('IDEMPOTENCY_CONFLICT');
    usedKeys.add(key);
    const params = new URLSearchParams();
    for (const [name, value] of Object.entries(body)) if (name !== 'target' && typeof value === 'string' && value) params.set(name, value);
    return piiZipResponse(target.base, [...target.header], target.rows(params));
  }),
];