// 환불 검토 화면의 목록 정렬·조건, 방문·유선 접수, 한도 검사, 승인·반려·보류, 승인자와 집행자 분리, 집행·재처리·이체 확인을 확인하는 시험
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
const field = (name: string) => screen.getByLabelText(new RegExp(`^${name}`));
const REFUND = (n: number) => `14${String(n).padStart(20, '0')}`;

async function open(n: number) {
  renderApp(`/pay/refunds/${REFUND(n)}`);
  await heading('환불 검토 상세');
}

async function decide(label: '승인' | '반려' | '보류', reason?: string) {
  await userEvent.click(within(screen.getByRole('form', { name: '환불 결정' })).getByRole('radio', { name: label }));
  if (reason) await userEvent.type(field('사유'), reason);
  await userEvent.click(screen.getByRole('button', { name: '결정 저장' }));
}

const confirmDecision = async () => userEvent.click(within(await screen.findByRole('group', { name: '결정 확정 확인' })).getByRole('button', { name: '확정' }));

describe('환불 목록', () => {
  it('접수·보류 건을 오래된 것부터 먼저 보이고 3영업일을 넘긴 건을 글자로 알린다', async () => {
    await signInAs('finance');
    renderApp('/pay/refunds');
    const list = await rows('환불 목록');
    expect(list.map((row) => cells(row)[0])).toEqual([
      'R20264-000012',
      'R20264-000011',
      'R20264-000013',
      'R20264-000014',
      'R20264-000015',
      'R20264-000017',
      'R20264-000006',
      'R20264-000016',
    ]);
    expect(cells(list[0]!)).toEqual(['R20264-000012', 'A20264-000201', '초급컴퓨터', '20,000원', '보류', '2026-09-07', '4일 · 3영업일 초과']);
    expect(cells(list[1]!)[6]).toBe('2일');
  });

  it('환불 상태·요청 주체·접수일 조건으로 좁힌다', async () => {
    await signInAs('finance');
    renderApp('/pay/refunds');
    await userEvent.selectOptions(await screen.findByLabelText('환불 상태'), '승인');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('환불 목록')).map((row) => cells(row)[0])).toEqual(['R20264-000013', 'R20264-000017']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.selectOptions(await screen.findByLabelText('요청 주체'), '담당자 대리 접수');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('환불 목록')).map((row) => cells(row)[0])).toEqual(['R20264-000012']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    fireEvent.change(await screen.findByLabelText('접수일 시작'), { target: { value: '2026-09-08' } });
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('환불 목록')).length).toBe(2));
  });

  it('환불 권한이 없는 강좌 담당자는 화면을 열 수 없다', async () => {
    await signInAs('course');
    renderApp('/pay/refunds');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('방문·유선 환불 접수', () => {
  async function receive(applicationNo: string, amount: string) {
    renderApp('/pay/refunds/new');
    await heading('방문·유선 환불 접수');
    await userEvent.type(field('신청번호'), applicationNo);
    await userEvent.type(field('요청액'), amount);
    await userEvent.type(field('환불 사유'), '본인 방문 요청');
    await userEvent.click(screen.getByRole('button', { name: '접수' }));
  }

  it('비워 두면 요청 없이 항목별로 알려 준다', async () => {
    await signInAs('finance');
    renderApp('/pay/refunds/new');
    await heading('방문·유선 환불 접수');
    await userEvent.click(screen.getByRole('button', { name: '접수' }));
    expect(screen.getAllByText('필수 항목입니다.').length).toBe(2);
    expect(screen.getByText('1원 이상의 금액을 입력해 주세요.')).toBeInTheDocument();
  });

  it('결제완료가 아닌 신청번호는 서버 오류를 신청번호 아래에 보인다', async () => {
    await signInAs('finance');
    await receive('A20264-999999', '10000');
    expect(await screen.findByText('결제완료된 신청번호를 확인해 주세요.')).toBeInTheDocument();
  });

  it('남은 환불 가능액을 넘으면 한도 초과 오류를 요청액 아래에 보인다', async () => {
    await signInAs('finance');
    await receive('A20264-000201', '50000'); // 원결제 60,000원 중 20,000원이 처리중으로 예약됨
    expect(await screen.findByText('환불 가능 금액을 초과합니다.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: '방문·유선 환불 접수' })).toBeInTheDocument();
  });

  it('접수하면 담당자 대리 접수로 열리고 접수 상태다', async () => {
    await signInAs('finance');
    await receive('A20264-000202', '20000');
    await heading('환불 검토 상세');
    expect(screen.getByText(/^접수 · 경과 0영업일/)).toBeInTheDocument();
    expect(screen.getByText(/담당자 대리 접수 · 박정산/)).toBeInTheDocument();
    expect(screen.getByText('기환불·예약 40,000원 / 남은 환불 가능 20,000원')).toBeInTheDocument();
  });
});

describe('환불 검토 결정', () => {
  it('한도·기준액·요청 내용을 보여 준다', async () => {
    await signInAs('finance');
    await open(11);
    expect(screen.getByText('기환불·예약 0원 / 남은 환불 가능 60,000원')).toBeInTheDocument();
    expect(screen.getByText('40,000원 (개강 후 당월분 제외) · 교육 시작 2026-10-01')).toBeInTheDocument();
    expect(screen.getByText(/증빙 1건/)).toBeInTheDocument();
    expect(screen.getByText(/회원 요청 · 오○○/)).toBeInTheDocument();
  });

  it('승인하면 확정 전에 한 번 더 확인하고 승인액이 이력에 남는다', async () => {
    await signInAs('finance');
    await open(11);
    await decide('승인');
    const group = await screen.findByRole('group', { name: '결정 확정 확인' });
    expect(within(group).getByText(/승인하면 승인액만큼 환불 한도가 예약됩니다/)).toBeInTheDocument();
    await userEvent.click(within(group).getByRole('button', { name: '확정' }));
    expect(await screen.findByText(/^승인 · 경과 2영업일/)).toBeInTheDocument();
    expect((await rows('환불 이력')).map((row) => cells(row).slice(1, 4))).toContainEqual(['승인', '박정산', '승인액 60,000원']);
    expect(screen.queryByRole('form', { name: '환불 결정' })).not.toBeInTheDocument();
    expect(screen.getByText('원결제 취소')).toBeInTheDocument();
  });

  it('승인액과 기존 예약액의 합이 원결제액을 넘으면 거절하고 확정 확인이 닫힌다', async () => {
    await signInAs('finance');
    await open(11);
    await userEvent.click(within(screen.getByRole('form', { name: '환불 결정' })).getByRole('radio', { name: '승인' }));
    await userEvent.clear(field('승인액'));
    await userEvent.type(field('승인액'), '70000');
    await userEvent.click(screen.getByRole('button', { name: '결정 저장' }));
    await confirmDecision();
    expect(await screen.findByText('환불 가능 금액을 초과합니다.')).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: '결정 확정 확인' })).not.toBeInTheDocument();
  });

  it('반려와 보류는 사유가 없으면 요청 없이 알려 주고 사유가 있으면 처리된다', async () => {
    await signInAs('finance');
    await open(11);
    await decide('반려');
    expect(screen.getByText('반려·보류는 사유가 필수입니다.', { selector: '.adm-field-error' })).toBeInTheDocument();
    await userEvent.type(field('사유'), '환불 기준에 해당하지 않습니다.');
    await userEvent.click(screen.getByRole('button', { name: '결정 저장' }));
    await confirmDecision();
    expect(await screen.findByText(/^반려 · 경과/)).toBeInTheDocument();
    expect(screen.getByText(/환불 기준에 해당하지 않습니다\./, { selector: 'dd' })).toBeInTheDocument();
  });

  it('보류한 건은 사유와 보류 해제 버튼만 보이고 해제하면 접수로 돌아간다', async () => {
    await signInAs('finance');
    await open(12);
    expect(screen.getByText('보류 사유: 증빙 확인 필요')).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: '환불 결정' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '보류 해제' }));
    expect(await screen.findByText(/^접수 · 경과 4영업일/)).toBeInTheDocument();
    expect(screen.getByRole('form', { name: '환불 결정' })).toBeInTheDocument();
  });

  it('보류하면 보류 상태가 된다', async () => {
    await signInAs('finance');
    await open(11);
    await decide('보류', '증빙 확인 중');
    await confirmDecision();
    expect(await screen.findByText(/^보류 · 경과/)).toBeInTheDocument();
    expect(screen.getByText('보류 사유: 증빙 확인 중')).toBeInTheDocument();
  });

  it('다른 곳에서 먼저 처리되었으면 안내한다', async () => {
    await signInAs('finance');
    await open(11);
    server.use(http.put('/api/admin/v1/refunds/:id/approve', () => apiError('VERSION_CONFLICT')));
    await decide('승인');
    await confirmDecision();
    expect(await screen.findByRole('alert')).toHaveTextContent('다른 곳에서 먼저 처리되었습니다.');
  });
});

describe('집행', () => {
  it('승인한 담당자는 같은 건을 집행할 수 없고 이유를 알려 준다', async () => {
    await signInAs('group');
    await open(11);
    await decide('승인');
    await confirmDecision();
    expect(await screen.findByText('승인한 담당자는 같은 환불 건을 집행할 수 없습니다. 다른 집행 담당자가 처리해 주세요.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /집행 요청/ })).not.toBeInTheDocument();
  });

  it('집행 권한이 없는 담당자는 승인된 건에도 집행 버튼이 없다', async () => {
    await signInAs('finance');
    await open(13);
    expect(screen.getByText('원결제 취소')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /집행 요청/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/집행할 수 없습니다/)).not.toBeInTheDocument();
  });

  it('다른 담당자가 두 번 확인해 집행을 요청하면 PG 취소 결과로 환불완료가 된다', async () => {
    await signInAs('group');
    await open(13);
    await userEvent.click(screen.getByRole('button', { name: '집행 요청 (R20264-000013)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 집행 요청 (R20264-000013)' }));
    expect(await screen.findByText(/^완료 · 경과/)).toBeInTheDocument();
    expect(screen.getByText('원결제가 취소되었습니다.')).toBeInTheDocument();
    expect(screen.getByText('김관리', { selector: 'dd' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /집행 요청/ })).not.toBeInTheDocument();
  });

  it('결제 담당자가 승인한 건을 다른 담당자가 집행하면 PG가 알려 주기 전까지 처리중이다', async () => {
    await signInAs('finance');
    const first = renderApp(`/pay/refunds/${REFUND(11)}`);
    await heading('환불 검토 상세');
    await decide('승인');
    await confirmDecision();
    await screen.findByText(/^승인 · 경과/);
    first.unmount();
    await signInAs('group');
    renderApp(`/pay/refunds/${REFUND(11)}`);
    await heading('환불 검토 상세');
    await userEvent.click(await screen.findByRole('button', { name: '집행 요청 (R20264-000011)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 집행 요청 (R20264-000011)' }));
    // 환불완료는 집행 결과가 확인된 뒤에만 보인다(FN-044).
    expect(await screen.findByText(/^처리중 · 경과/)).toBeInTheDocument();
    expect(screen.getByText('PG 결과를 확인하는 중입니다.')).toBeInTheDocument();
  });

  it('수동 계좌환불은 집행을 요청해도 이체 완료를 확인하기 전까지 처리중이다', async () => {
    await signInAs('group');
    await open(17);
    expect(screen.queryByRole('button', { name: /이체 완료 확인/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '집행 요청 (R20264-000017)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 집행 요청 (R20264-000017)' }));
    expect(await screen.findByText(/^처리중 · 경과/)).toBeInTheDocument();
    expect(screen.getByText('이체 대기 중입니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '이체 완료 확인 (R20264-000017)' })).toBeInTheDocument();
  });
  it('집행에 실패한 건은 재처리로 같은 환불 건을 다시 집행한다', async () => {
    await signInAs('group');
    await open(15);
    expect(screen.getByText('PG 취소 요청이 실패했습니다.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '재처리 (R20264-000015)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 재처리 (R20264-000015)' }));
    expect(await screen.findByText(/^완료 · 경과/)).toBeInTheDocument();
    expect((await rows('환불 이력')).length).toBe(4);
  });

  it('수동 계좌환불은 마스킹된 계좌를 보이고 이체 완료를 확인해야 환불완료가 된다', async () => {
    await signInAs('group');
    await open(14);
    expect(screen.getByText('국민은행 · 김○○ · 123-****-**89')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '이체 완료 확인 (R20264-000014)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 이체 완료 확인 (R20264-000014)' }));
    expect(await screen.findByText(/^완료 · 경과/)).toBeInTheDocument();
    expect(screen.getByText('이체가 완료되었습니다.')).toBeInTheDocument();
  });

  it('이미 환불완료된 건에는 조치 버튼이 없다', async () => {
    await signInAs('group');
    await open(6);
    expect(screen.getByText('원결제가 취소되었습니다.')).toBeInTheDocument();
    expect(within(screen.getByRole('main')).queryByRole('button')).not.toBeInTheDocument();
  });

  it('두 번 확인 단계에서 취소하면 집행하지 않는다', async () => {
    await signInAs('group');
    await open(13);
    await userEvent.click(screen.getByRole('button', { name: '집행 요청 (R20264-000013)' }));
    await userEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(screen.getByRole('button', { name: '집행 요청 (R20264-000013)' })).toBeInTheDocument();
    expect(screen.getByText(/^승인 · 경과/)).toBeInTheDocument();
  });
});