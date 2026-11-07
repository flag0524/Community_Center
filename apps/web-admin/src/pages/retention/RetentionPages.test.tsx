// 보존·파기 검토(예정 목록, 정산자료 제외 안내, 보존기간 미정 자료 실행 금지, 확인한 건수로 두 번 확인 실행, 실행 결과 기록)를 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';
import { apiError } from '../../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);
const ITEM = (n: number) => `92${String(n).padStart(20, '0')}`;
const fact = (name: string) => screen.getByText(name, { selector: 'dt' }).nextElementSibling?.textContent;
const run = async () => {
  await userEvent.click(screen.getByRole('button', { name: '실행 (탈퇴 회원 개인정보 3건)' }));
  await userEvent.click(screen.getByRole('button', { name: '정말 실행 (탈퇴 회원 개인정보 3건)' }));
};

describe('보존·파기 목록', () => {
  it('파기 예정 자료의 건수·기준일·예정일·상태를 보이고 보존기간 미정은 미정으로 구분한다', async () => {
    await signInAs('group');
    renderApp('/sys/retention');
    expect((await rows('파기 예정 목록')).map((row) => cells(row))).toEqual([
      ['탈퇴 회원 개인정보', '3건', '2026-10-05', '2026-11-04', '예정일 지남'],
      ['인증 기록(OTP·세션·로그인 실패)', '140건', '2026-10-01', '2026-10-31', '예정일 지남'],
      ['업무 감사이력', '12건', '2023-11-01', '2026-11-01', '검토 전용'],
      ['수동환불 계좌정보', '5건', '-', '미정', '기간 미정'],
      ['문자 문안·수신명단', '40건', '-', '미정', '기간 미정'],
    ]);
  });

  it('정산자료가 목록에서 빠진다는 사실과 이유를 알린다', async () => {
    await signInAs('group');
    renderApp('/sys/retention');
    expect(await screen.findByText('정산자료(결제·환불 원장)는 이 목록에서 제외됩니다. 법정 보존 5년 대상이라 탈퇴와 관계없이 파기하지 않습니다.')).toBeInTheDocument();
  });

  it('감사 조회 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('finance');
    renderApp('/sys/retention');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('보존·파기 상세와 실행', () => {
  it('처리 항목과 보존 규칙을 보이고 실행한 적이 없으면 기록이 없다고 알린다', async () => {
    await signInAs('group');
    renderApp(`/sys/retention/${ITEM(1)}`);
    await heading('보존·파기 상세');
    expect(fact('보존 규칙')).toMatch(/탈퇴 후 30일이 지난 회원/);
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['이름', '휴대전화', '이메일']);
    expect(screen.getByText('실행한 기록이 없습니다.')).toBeInTheDocument();
    expect(screen.getByText('실행하면 되돌릴 수 없습니다. 지금 3건이 대상입니다.')).toBeInTheDocument();
  });

  it('두 번 확인해 실행하면 처리 건수가 기록되고 대상이 0건이 되어 다시 실행할 수 없다', async () => {
    await signInAs('group');
    renderApp(`/sys/retention/${ITEM(1)}`);
    await heading('보존·파기 상세');
    await run();
    expect(await screen.findByText('실행했습니다. 3건을 처리했습니다.')).toBeInTheDocument();
    expect(fact('건수')).toBe('0건');
    expect((await rows('실행 결과 기록')).map((row) => cells(row).slice(1))).toEqual([['김관리', '3건']]);
    expect(screen.queryByRole('button', { name: /^실행/ })).not.toBeInTheDocument();
  });

  it('실행 요청에 확인한 건수와 멱등키를 싣는다', async () => {
    let sent: { body?: { expectedCount?: number }; key: string | null } = { key: null };
    server.use(
      http.post('/api/admin/v1/retention/:id/execute', async ({ request }) => {
        sent = { body: (await request.json()) as { expectedCount?: number }, key: request.headers.get('Idempotency-Key') };
        return apiError('RULE_REJECTED', { itemId: '시험용 거절' });
      }),
    );
    await signInAs('group');
    renderApp(`/sys/retention/${ITEM(1)}`);
    await heading('보존·파기 상세');
    await run();
    await screen.findByText('시험용 거절');
    expect(sent.body?.expectedCount).toBe(3);
    expect(sent.key).toBeTruthy();
  });

  it('확인한 뒤 대상이 바뀌면 안내하고 다시 센 건수를 보여 다시 확인받는다', async () => {
    await signInAs('group');
    renderApp(`/sys/retention/${ITEM(1)}`);
    await heading('보존·파기 상세');
    server.use(http.post('/api/admin/v1/retention/:id/execute', () => apiError('CONFLICT_STATE', { expectedCount: '대상이 바뀌었습니다. 현재 5건입니다.' }), { once: true }), http.get('/api/admin/v1/retention/:id', () => Response.json({ itemId: ITEM(1), target: 'WITHDRAWN_MEMBER', count: 5, baseDate: '2026-10-05', dueOn: '2026-11-04', state: 'DUE', rule: '규칙', fields: ['이름'], executions: [], canExecute: true }), { once: true }));
    await run();
    expect(await screen.findByText('확인한 뒤 대상이 바뀌었습니다. 아래 건수를 다시 확인해 주세요.')).toBeInTheDocument();
    await waitFor(() => expect(fact('건수')).toBe('5건'));
  });

  it('화면이 본 건수와 서버가 센 건수가 다르면 서버가 실행을 거절한다', async () => {
    server.use(http.get('/api/admin/v1/retention/:id', () => Response.json({ itemId: ITEM(1), target: 'WITHDRAWN_MEMBER', count: 99, baseDate: '2026-10-05', dueOn: '2026-11-04', state: 'DUE', rule: '규칙', fields: ['이름'], executions: [], canExecute: true })));
    await signInAs('group');
    renderApp(`/sys/retention/${ITEM(1)}`);
    await heading('보존·파기 상세');
    await userEvent.click(screen.getByRole('button', { name: '실행 (탈퇴 회원 개인정보 99건)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 실행 (탈퇴 회원 개인정보 99건)' }));
    expect(await screen.findByText('확인한 뒤 대상이 바뀌었습니다. 아래 건수를 다시 확인해 주세요.')).toBeInTheDocument();
  });

  it('예정일이 지나지 않은 자료를 실행하면 서버가 이유를 알린다', async () => {
    server.use(http.get('/api/admin/v1/retention/:id', () => Response.json({ itemId: ITEM(4), target: 'REFUND_ACCOUNT', count: 5, baseDate: null, dueOn: null, state: 'PERIOD_TBD', rule: '규칙', fields: ['수동환불 계좌정보'], executions: [], canExecute: true })));
    await signInAs('group');
    renderApp(`/sys/retention/${ITEM(4)}`);
    await heading('보존·파기 상세');
    await userEvent.click(screen.getByRole('button', { name: '실행 (수동환불 계좌정보 5건)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 실행 (수동환불 계좌정보 5건)' }));
    expect(await screen.findByText('예정일이 지난 자료만 실행할 수 있습니다.')).toBeInTheDocument();
  });

  it.each([
    ['보존기간이 정해지지 않은 자료', 4, '보존기간이 정해지기 전에는 실행할 수 없습니다.'],
    ['검토 전용 자료', 3, '이 자료는 검토만 하고 이 화면에서 실행하지 않습니다.'],
  ])('%s는 실행 버튼 없이 이유를 알린다', async (_name, n, notice) => {
    await signInAs('group');
    renderApp(`/sys/retention/${ITEM(n)}`);
    await heading('보존·파기 상세');
    expect(screen.getByText(notice)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^실행/ })).not.toBeInTheDocument();
  });

  it('서버가 실행 불가로 알리면 실행 버튼을 보이지 않는다', async () => {
    server.use(http.get('/api/admin/v1/retention/:id', () => Response.json({ itemId: ITEM(1), target: 'WITHDRAWN_MEMBER', count: 3, baseDate: '2026-10-05', dueOn: '2026-11-04', state: 'DUE', rule: '규칙', fields: ['이름'], executions: [], canExecute: false })));
    await signInAs('group');
    renderApp(`/sys/retention/${ITEM(1)}`);
    await heading('보존·파기 상세');
    expect(screen.queryByRole('button', { name: /^실행/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/되돌릴 수 없습니다/)).not.toBeInTheDocument();
  });
});