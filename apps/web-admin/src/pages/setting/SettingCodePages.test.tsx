// 운영 설정(읽기 전용, 검토 상태 구분)과 공통 코드(표시명·순서·사용만 편집, 참조 확인 실패 구분, 저장 거절 시 입력 유지)를 확인하는 시험
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';
import { apiError } from '../../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);
const SETTING = (n: number) => `90${String(n).padStart(20, '0')}`;
const fact = (name: string) => screen.getByText(name, { selector: 'dt' }).nextElementSibling?.textContent;
const nameInput = (code: string) => screen.getByLabelText(`${code} 표시명`) as HTMLInputElement;
const seqInput = (code: string) => screen.getByLabelText(`${code} 순서`) as HTMLInputElement;
const save = () => userEvent.click(screen.getByRole('button', { name: '저장' }));

describe('운영 설정', () => {
  it('운영 기준과 검토 상태를 읽기 전용으로 보인다', async () => {
    await signInAs('group');
    renderApp('/sys/settings');
    expect((await rows('운영 기준 목록')).map((row) => cells(row))).toEqual([
      ['결제 기한', '600초', '확정', '2026-10-27'],
      ['환불 당월분 공식', '당월 사용분 일할 공제(안)', '검토 중', '2026-10-29'],
      ['결제 대행사(PG)', 'TBD', '보류', '2026-10-23'],
      ['문자 발송 공급자', 'TBD (후보: NHN Cloud SMS, 알리고, 솔라피)', '보류', '2026-10-23'],
      ['감면율', '50%', '확정', '2026-10-27'],
    ]);
    expect(screen.getByText(/확정은 기준이 정해졌다는 뜻이며 실제 기능에 적용이 끝났다는 뜻은 아닙니다/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /수정|저장|삭제/ })).not.toBeInTheDocument();
  });

  it('상태와 항목명으로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/sys/settings');
    await rows('운영 기준 목록');
    await userEvent.selectOptions(screen.getByLabelText('상태'), '보류');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('운영 기준 목록')).length).toBe(2));
    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.type(await screen.findByLabelText('항목명'), '감면');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('운영 기준 목록')).map((row) => cells(row)[0])).toEqual(['감면율']));
  });

  it('상세는 설명·근거와 버전을 보인다', async () => {
    await signInAs('group');
    renderApp(`/sys/settings/${SETTING(2)}`);
    await heading('운영 기준 상세');
    expect(fact('상태')).toBe('검토 중');
    expect(fact('버전')).toBe('1');
    expect(fact('설명·근거')).toMatch(/기관과 협의 중/);
  });

  it('사이트 관리 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('course');
    renderApp('/sys/settings');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('공통 코드', () => {
  it('첫 그룹의 코드를 순서대로 보이고 참조 건수를 함께 보인다', async () => {
    await signInAs('group');
    renderApp('/sys/codes');
    const list = await rows('코드 목록');
    expect(list.map((row) => [cells(row)[0], cells(row)[4]])).toEqual([
      ['ES.WAIT', '312건'],
      ['ES.HOLD', '41건'],
      ['ES.CONFIRM', '1,204건'],
      ['ES.CANCEL', '87건'],
      ['ES.EXPIRE', '23건'],
      ['ES.COMPLETE', '0건'],
    ]);
    expect(nameInput('ES.WAIT').value).toBe('대기');
    expect(screen.queryByRole('button', { name: /삭제|추가/ })).not.toBeInTheDocument();
  });

  it('참조 건수를 확인하지 못하면 0건이 아니라 확인 실패로 보인다', async () => {
    await signInAs('group');
    renderApp('/sys/codes?group=FS');
    const list = await rows('코드 목록');
    expect(list.map((row) => [cells(row)[0], cells(row)[4]])).toContainEqual(['FS.DELETE', '확인 실패']);
  });

  it('그룹·검색어·사용 여부로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/sys/codes');
    await rows('코드 목록');
    await userEvent.selectOptions(screen.getByLabelText('코드 그룹'), '감면사전심사상태');
    await userEvent.selectOptions(screen.getByLabelText('사용'), '사용 안 함');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('코드 목록')).map((row) => cells(row)[0])).toEqual(['DS.REVOKED']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await rows('코드 목록');
    await userEvent.type(screen.getByLabelText('검색어'), '취소');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('코드 목록')).map((row) => cells(row)[0])).toEqual(['ES.CANCEL']));
  });

  it('표시명·순서·사용 여부를 한 번에 저장하고 저장한 값이 서버에 남는다', async () => {
    await signInAs('group');
    renderApp('/sys/codes');
    await rows('코드 목록');
    await userEvent.clear(nameInput('ES.WAIT'));
    await userEvent.type(nameInput('ES.WAIT'), '대기중');
    await userEvent.clear(seqInput('ES.WAIT'));
    await userEvent.type(seqInput('ES.WAIT'), '5');
    await userEvent.click(screen.getByLabelText('ES.COMPLETE 사용'));
    await save();
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    const saved = (await (await fetch('/api/admin/v1/codes?group=ES')).json()) as { items: Array<{ code: string; name: string; sortSeq: number; use: boolean }> };
    expect(saved.items.find((item) => item.code === 'ES.WAIT')).toMatchObject({ name: '대기중', sortSeq: 5 });
    expect(saved.items.find((item) => item.code === 'ES.COMPLETE')?.use).toBe(false);
  });

  it('다른 그룹도 그 그룹의 코드로 저장한다', async () => {
    await signInAs('group');
    renderApp('/sys/codes?group=FS');
    await rows('코드 목록');
    await userEvent.clear(nameInput('FS.SAFE'));
    await userEvent.type(nameInput('FS.SAFE'), '정상');
    await save();
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    const saved = (await (await fetch('/api/admin/v1/codes?group=FS')).json()) as { items: Array<{ code: string; name: string }> };
    expect(saved.items.find((item) => item.code === 'FS.SAFE')?.name).toBe('정상');
  });

  it('그룹을 고르지 않으면 목록의 첫 그룹을 보인다', async () => {
    server.use(http.get('/api/admin/v1/code-groups', () => Response.json({ items: [{ id: 'OR', name: '운영기준검토상태' }, { id: 'ES', name: '수강신청상태' }] })));
    await signInAs('group');
    renderApp('/sys/codes');
    expect((await rows('코드 목록')).map((row) => cells(row)[0])).toEqual(['OR.REVIEW', 'OR.DECIDED', 'OR.HOLD']);
  });

  it('조건을 바꾸면 이전 조건에서 고친 값이 새 목록에 섞이지 않는다', async () => {
    await signInAs('group');
    renderApp('/sys/codes');
    await rows('코드 목록');
    await userEvent.clear(nameInput('ES.WAIT'));
    await userEvent.type(nameInput('ES.WAIT'), '고친 이름');
    await userEvent.type(screen.getByLabelText('검색어'), '대기');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('코드 목록')).map((row) => cells(row)[0])).toEqual(['ES.WAIT', 'ES.HOLD']));
    expect(nameInput('ES.WAIT').value).toBe('대기');
  });

  it('저장 요청에는 그룹과 보이는 모든 코드의 값만 싣는다', async () => {
    let sent: { groupId?: string; items?: Array<Record<string, unknown>> } = {};
    server.use(
      http.put('/api/admin/v1/codes', async ({ request }) => {
        sent = (await request.json()) as typeof sent;
        return apiError('RULE_REJECTED', { 'ES.HOLD.name': '시험용 거절' });
      }),
    );
    await signInAs('group');
    renderApp('/sys/codes');
    await rows('코드 목록');
    await userEvent.clear(nameInput('ES.HOLD'));
    await userEvent.type(nameInput('ES.HOLD'), '결제 대기');
    await save();
    await screen.findByText('시험용 거절');
    expect(sent.groupId).toBe('ES');
    expect(sent.items).toHaveLength(6);
    expect(sent.items?.[1]).toEqual({ code: 'ES.HOLD', name: '결제 대기', sortSeq: 20, use: true });
  });

  it('표시명이 비었거나 순서가 숫자가 아니면 요청 없이 안내하고 입력을 그대로 둔다', async () => {
    let calls = 0;
    server.use(
      http.put('/api/admin/v1/codes', () => {
        calls += 1;
        return apiError('RULE_REJECTED');
      }),
    );
    await signInAs('group');
    renderApp('/sys/codes');
    await rows('코드 목록');
    await userEvent.clear(nameInput('ES.WAIT'));
    fireEvent.change(seqInput('ES.HOLD'), { target: { value: 'abc' } });
    await save();
    expect(screen.getByText('표시명을 입력해 주세요.')).toBeInTheDocument();
    expect(screen.getByText('0 이상의 정수를 입력해 주세요.')).toBeInTheDocument();
    expect(seqInput('ES.HOLD').value).toBe('abc');
    expect(calls).toBe(0);
  });

  it('서버가 저장을 거절하면 사유를 보이고 입력은 그대로 둔다', async () => {
    server.use(http.put('/api/admin/v1/codes', () => apiError('RULE_REJECTED', { 'ES.WAIT.name': '이미 쓰는 이름입니다.' })));
    await signInAs('group');
    renderApp('/sys/codes');
    await rows('코드 목록');
    await userEvent.clear(nameInput('ES.WAIT'));
    await userEvent.type(nameInput('ES.WAIT'), '취소');
    await save();
    expect(await screen.findByText('이미 쓰는 이름입니다.')).toBeInTheDocument();
    expect(nameInput('ES.WAIT').value).toBe('취소');
    expect(screen.queryByText('저장했습니다.')).not.toBeInTheDocument();
  });

  it('코드 관리 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('finance');
    renderApp('/sys/codes');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});