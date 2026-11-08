// 개인식별 명단 암호화 내보내기(두 단계 확인, 진짜 AES-256 ZIP, 올바른 암호로만 열림, 암호 한 번만 표시, 권한 차이, 5천 행 상한)를 확인하는 시험
import { Uint8ArrayReader, Uint8ArrayWriter, ZipReader } from '@zip.js/zip.js';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { requestPiiExport } from '../api/piiExport';
import { DEMO_ADMINS } from '../mocks/auth';
import { exportLog } from '../mocks/csv';
import { newPassword, PII_MAX_ROWS, piiZipResponse } from '../mocks/pii';
import { renderApp, server, signInAs, useMockServer } from '../test/render';

useMockServer();

let saved: { blob: Blob; name: string }[] = [];
let blobOf: Blob | null = null;

beforeEach(() => {
  saved = [];
  blobOf = null;
  URL.createObjectURL = vi.fn((blob: Blob | MediaSource) => {
    blobOf = blob as Blob;
    return 'blob:test';
  });
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    saved.push({ blob: blobOf!, name: this.download });
  });
});

afterEach(() => vi.restoreAllMocks());

const request = () => screen.findByRole('button', { name: '암호화 파일 요청' });
const confirm = async () => {
  await userEvent.click(await request());
  await userEvent.click(within(await screen.findByRole('group', { name: '암호화 파일 요청 확인' })).getByRole('button', { name: '요청하기' }));
};
const passwordOf = async () => (await screen.findByRole('group', { name: '암호화 파일 암호' })).querySelector('code')!.textContent!;

/** ZIP 첫 항목을 연다. 암호가 없거나 틀리면 getData가 던진다. */
async function open(blob: Blob, password?: string) {
  const reader = new ZipReader(new Uint8ArrayReader(new Uint8Array(await blob.arrayBuffer())), { useWebWorkers: false });
  const [entry] = await reader.getEntries();
  if (!entry || entry.directory) throw new Error('파일 항목이 없습니다.');
  const bytes = await entry.getData!(new Uint8ArrayWriter(), { password });
  await reader.close();
  return { entry, text: new TextDecoder().decode(bytes).replace(/^\uFEFF/, '') };
}

describe('암호화 파일 요청 화면', () => {
  it('두 단계로 확인한 뒤 AES-256 ZIP을 받고 암호는 올바른 암호로만 열린다', async () => {
    await signInAs('group');
    renderApp('/mbr/members');
    await confirm();
    await waitFor(() => expect(saved.length).toBe(1));
    expect(saved[0]!.name).toBe('members-pii.zip');
    const password = await passwordOf();
    expect(password).toMatch(/^[A-HJ-NP-Za-km-z2-9]{16}$/);

    const { entry, text } = await open(saved[0]!.blob, password);
    expect(entry.filename).toBe('members.csv');
    expect(entry.encrypted).toBe(true);
    expect(entry.zipCrypto).toBe(false);
    expect(entry.extraFieldAES?.strength).toBe(3); // 3 = AES-256
    expect(text).toContain('아이디,이름,연락처,이메일,가입일,상태');
    expect(text).toContain('jori_kim,김지원,010-0000-0001,member1@example.invalid,2026-08-20,ACTIVE');
    await expect(open(saved[0]!.blob)).rejects.toThrow();
    await expect(open(saved[0]!.blob, `${password}x`)).rejects.toThrow();
  });

  it('요청하기 전에 취소하면 파일도 작업이력도 만들지 않는다', async () => {
    await signInAs('group');
    renderApp('/mbr/members');
    await userEvent.click(await request());
    const ask = await screen.findByRole('group', { name: '암호화 파일 요청 확인' });
    expect(ask).toHaveTextContent('가려지지 않은');
    await userEvent.click(within(ask).getByRole('button', { name: '취소' }));
    expect(screen.queryByRole('group', { name: '암호화 파일 요청 확인' })).toBeNull();
    expect(saved).toEqual([]);
    expect(exportLog).toEqual([]);
  });

  it('암호는 닫으면 화면에서 사라지고 다시 요청하면 새 암호가 나오며 작업이력에는 건수만 남는다', async () => {
    await signInAs('group');
    renderApp('/mbr/members');
    await confirm();
    const first = await passwordOf();
    await userEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(screen.queryByText(first)).toBeNull();
    expect(screen.queryByRole('group', { name: '암호화 파일 암호' })).toBeNull();

    await confirm();
    await waitFor(() => expect(saved.length).toBe(2));
    const second = await passwordOf();
    expect(second).not.toBe(first);
    expect(exportLog).toEqual([
      { name: 'members-pii.zip', rows: 6 },
      { name: 'members-pii.zip', rows: 6 },
    ]);
    expect(JSON.stringify(exportLog)).not.toContain(first);
    expect(JSON.stringify(exportLog)).not.toContain(second);
  });

  it('암호 복사는 클립보드에 쓰고 복사했다고 알리며 쓰지 못하면 알리지 않는다', async () => {
    const writeText = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('denied'));
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    await signInAs('group');
    renderApp('/mbr/members');
    await confirm();
    const password = await passwordOf();
    await userEvent.click(screen.getByRole('button', { name: '암호 복사' }));
    expect(await screen.findByText('복사했습니다.')).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(password);
    await userEvent.click(screen.getByRole('button', { name: '암호 복사' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText('복사했습니다.')).toBeNull());
  });

  it('수강신청은 목록의 조건을 그대로 반영하고 실제 이름과 연락처를 담는다', async () => {
    await signInAs('group');
    renderApp('/pay/applications?status=WAITING');
    await confirm();
    await waitFor(() => expect(saved.length).toBe(1));
    expect(saved[0]!.name).toBe('applications-pii.zip');
    const { text } = await open(saved[0]!.blob, await passwordOf());
    const lines = text.split('\r\n').filter(Boolean);
    expect(lines[0]).toBe('신청번호,신청자,연락처,강좌,신청상태,접수시각');
    expect(lines.length).toBe(1 + 3);
    expect(lines.slice(1).every((line) => !line.includes('○'))).toBe(true);
  });

  it('내보내기 권한이 없으면 버튼이 없고 있으면 보인다', async () => {
    await signInAs('finance');
    const first = renderApp('/pay/applications');
    await screen.findByRole('region', { name: '수강신청 목록' });
    expect(screen.queryByRole('button', { name: '암호화 파일 요청' })).toBeNull();
    expect(screen.getByRole('button', { name: 'CSV 내려받기' })).toBeInTheDocument(); // 가려진 CSV는 그대로 쓸 수 있다
    first.unmount();
    await signInAs('group');
    renderApp('/pay/applications');
    expect(await request()).toBeInTheDocument();
  });

  it('서버가 거절하면 사유를 알리고 암호 안내를 띄우지 않는다', async () => {
    await signInAs('group');
    renderApp('/mbr/members');
    server.use(
      http.post('/api/admin/v1/exports/pii', () =>
        HttpResponse.json({ code: 'RULE_REJECTED', message: '내려받을 행이 5천 건을 넘습니다. 조건을 좁혀 주세요.', fields: null, requestId: 'x' }, { status: 422 }),
      ),
    );
    await confirm();
    expect(await screen.findByRole('alert')).toHaveTextContent('5천 건을 넘습니다');
    expect(screen.queryByRole('group', { name: '암호화 파일 암호' })).toBeNull();
    expect(saved).toEqual([]);
  });
});

describe('모의 서버의 내보내기 규칙', () => {
  it('같은 멱등키로 다시 보내면 암호를 다시 줄 수 없어 409로 거절한다', async () => {
    await signInAs('group');
    const body = { target: 'MEMBERS' } as const;
    await requestPiiExport(body, 'key-1');
    await expect(requestPiiExport(body, 'key-1')).rejects.toMatchObject({ status: 409 });
    await expect(requestPiiExport(body, 'key-2')).resolves.toBeDefined();
  });

  it('내보내기 권한이 없으면 거절한다', async () => {
    await signInAs('course');
    await expect(requestPiiExport({ target: 'APPLICATIONS' }, 'key-3')).rejects.toMatchObject({ status: 403 });
  });

  it('내보내기 권한이 있어도 그 목록을 볼 권한이 없으면 거절한다', async () => {
    const group = DEMO_ADMINS.group.authorities as string[];
    const original = [...group];
    try {
      await signInAs('group');
      await expect(requestPiiExport({ target: 'MEMBERS' }, 'key-4')).resolves.toBeDefined();
      group.splice(group.indexOf('AU.MBR_R'), 1); // 내보내기 권한은 그대로 두고 회원 조회 권한만 뺀다
      await expect(requestPiiExport({ target: 'MEMBERS' }, 'key-5')).rejects.toMatchObject({ status: 403 });
      await expect(requestPiiExport({ target: 'APPLICATIONS' }, 'key-6')).resolves.toBeDefined();
    } finally {
      group.splice(0, group.length, ...original);
    }
  });

  it('5천 행까지는 만들고 넘으면 거절하며 거절하면 작업이력을 남기지 않는다', async () => {
    const rows = Array.from({ length: PII_MAX_ROWS + 1 }, (_, i) => [`행${i}`]);
    const over = await piiZipResponse('t', ['a'], rows);
    expect(over.status).toBe(422);
    expect(exportLog).toEqual([]);
    const ok = await piiZipResponse('t', ['a'], rows.slice(1));
    expect(ok.status).toBe(200);
    expect(ok.headers.get('X-Export-Password')).toHaveLength(16);
    expect(ok.headers.get('Cache-Control')).toBe('private, no-store');
  });

  it('암호는 16자이고 헷갈리는 글자를 쓰지 않으며 매번 다르다', () => {
    const passwords = Array.from({ length: 50 }, () => newPassword());
    expect(new Set(passwords).size).toBe(50);
    expect(passwords.every((password) => /^[A-HJ-NP-Za-km-z2-9]{16}$/.test(password))).toBe(true);
  });
});