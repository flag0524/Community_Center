// 결제·거래 대조 화면의 목록 정렬·탭·조건, 상세 통보·조치 이력, PG 재조회, 근거와 승인번호가 필요한 수동 대사, 권한 차이를 확인하는 시험
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
const TXN = (n: number) => `13${String(n).padStart(20, '0')}`;

describe('거래 목록', () => {
  it('결과 확인 중인 거래를 먼저 보이고 그 안에서는 최근 요청이 앞이다', async () => {
    await signInAs('finance');
    renderApp('/pay/transactions');
    const list = await rows('거래 목록');
    expect(list.map((row) => cells(row)[0])).toEqual([
      'ORD-20260907-000006',
      'ORD-20260907-000003',
      'ORD-20260907-000002',
      'ORD-20260907-000005',
      'ORD-20260907-000004',
      'ORD-20260907-000001',
    ]);
    expect(cells(list[2]!)).toEqual(['ORD-20260907-000002', 'A20264-000203', '60,000원', '카드', '승인 결과 확인 중', '2026-09-07 10:01', '-', '3']);
  });

  it('충돌 통보 건 탭은 충돌로 격리된 통보가 있는 거래만 모은다', async () => {
    await signInAs('finance');
    renderApp('/pay/transactions');
    await userEvent.click(await screen.findByRole('link', { name: '충돌 통보 건' }));
    await waitFor(async () => expect((await rows('거래 목록')).map((row) => cells(row)[0])).toEqual(['ORD-20260907-000002']));
    expect(screen.getByRole('link', { name: '충돌 통보 건' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: '전체 거래' })).not.toHaveAttribute('aria-current');
  });

  it('결제 상태·결제수단·검색어·요청일 조건으로 좁힌다', async () => {
    await signInAs('finance');
    renderApp('/pay/transactions');
    await userEvent.selectOptions(await screen.findByLabelText('결제 상태'), '결제완료');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('거래 목록')).length).toBe(2));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.selectOptions(await screen.findByLabelText('결제수단'), '계좌이체');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('거래 목록')).map((row) => cells(row)[0])).toEqual(['ORD-20260907-000003', 'ORD-20260907-000005']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.type(await screen.findByLabelText('검색어'), 'A20264-000303');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('거래 목록')).length).toBe(1));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    fireEvent.change(await screen.findByLabelText('요청일 시작'), { target: { value: '2026-09-09' } });
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('거래 목록')).length).toBe(2));
  });

  it('결제 조회 권한이 없는 강좌 담당자는 화면을 열 수 없다', async () => {
    await signInAs('course');
    renderApp('/pay/transactions');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('거래 상세', () => {
  it('결과 확인 중인 거래는 재조회 횟수·통보 이력(충돌 포함)과 조치 안내를 보인다', async () => {
    await signInAs('finance');
    renderApp(`/pay/transactions/${TXN(2)}`);
    await heading('결제·거래 상세');
    expect(screen.getByText('승인 결과 확인 중 · 재조회 3/3 (마지막 10:07)')).toBeInTheDocument();
    expect((await rows('PG 통보 이력')).map((row) => cells(row)[2])).toEqual(['처리 완료', '중복(기존 결과 반환)', '충돌(격리, 보안사건)']);
    expect(screen.getByText('확인되지 않은 상태를 임의로 실패·취소 처리하지 마세요. PG 관리자 화면에서 확인한 결과만 입력합니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'PG 재조회' })).toBeInTheDocument();
    expect(screen.getByText('조치 이력이 없습니다.')).toBeInTheDocument();
    expect(screen.getByText('연결된 환불이 없습니다.')).toBeInTheDocument();
  });

  it('PG가 결과를 알려 주지 않으면 상태는 그대로이고 조치 이력만 남는다', async () => {
    await signInAs('finance');
    renderApp(`/pay/transactions/${TXN(2)}`);
    await heading('결제·거래 상세');
    await userEvent.click(screen.getByRole('button', { name: 'PG 재조회' }));
    const history = (await rows('조치 이력')).map(cells);
    expect(history[0]!.slice(1)).toEqual(['PG 재조회', '박정산', 'PG가 결과를 알려 주지 않았습니다. 상태는 그대로입니다.']);
    expect(screen.getByText(/^승인 결과 확인 중 · 재조회 3\/3/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'PG 재조회' })).toBeInTheDocument();
  });

  it('PG가 승인을 확인해 주면 결제완료가 되고 조치 영역이 사라진다', async () => {
    await signInAs('finance');
    renderApp(`/pay/transactions/${TXN(3)}`);
    await heading('결제·거래 상세');
    await userEvent.click(screen.getByRole('button', { name: 'PG 재조회' }));
    expect(await screen.findByText('PG에서 승인을 확인했습니다.')).toBeInTheDocument();
    expect(screen.getByText(/^결제완료/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'PG 재조회' })).not.toBeInTheDocument();
    expect(screen.queryByRole('form', { name: '수동 대사' })).not.toBeInTheDocument();
  });

  it('이미 결제된 거래에는 조치가 없고 연결된 환불을 보인다', async () => {
    await signInAs('finance');
    renderApp(`/pay/transactions/${TXN(5)}`);
    await heading('결제·거래 상세');
    expect(screen.getByText('R20264-000011 · 60,000원 · 접수')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'PG 재조회' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '조치' })).not.toBeInTheDocument();
  });
});

describe('수동 대사', () => {
  const form = () => screen.getByRole('form', { name: '수동 대사' });

  async function open(n: number) {
    renderApp(`/pay/transactions/${TXN(n)}`);
    await heading('결제·거래 상세');
  }

  it('결과와 근거를 비워 두면 요청 없이 항목별로 알려 준다', async () => {
    await signInAs('finance');
    const requested: string[] = [];
    server.events.on('request:start', ({ request }) => requested.push(`${request.method} ${new URL(request.url).pathname}`));
    await open(6);
    await userEvent.click(within(form()).getByRole('button', { name: '대사 결과 저장' }));
    server.events.removeAllListeners();
    expect(screen.getByText('대사 결과를 선택해 주세요.')).toBeInTheDocument();
    expect(screen.getByText('확인 근거는 필수입니다.')).toBeInTheDocument();
    expect(requested.filter((request) => request.includes('manual-reconcile'))).toEqual([]);
  });

  it('성공으로 처리하려면 PG 승인번호가 필요하다', async () => {
    await signInAs('finance');
    await open(6);
    await userEvent.click(within(form()).getByRole('radio', { name: '성공' }));
    await userEvent.type(within(form()).getByLabelText(/^확인 근거/), 'PG 관리자 화면에서 승인 확인');
    await userEvent.click(within(form()).getByRole('button', { name: '대사 결과 저장' }));
    expect(screen.getByText('성공으로 처리하려면 PG 승인번호가 필요합니다.')).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: '대사 확정 확인' })).not.toBeInTheDocument();
  });

  it('확정 전에 한 번 더 확인하고 취소하면 그대로 돌아간다', async () => {
    await signInAs('finance');
    await open(6);
    await userEvent.click(within(form()).getByRole('radio', { name: '실패' }));
    await userEvent.type(within(form()).getByLabelText(/^확인 근거/), 'PG 관리자 화면에서 실패 확인');
    await userEvent.click(within(form()).getByRole('button', { name: '대사 결과 저장' }));
    const confirm = screen.getByRole('group', { name: '대사 확정 확인' });
    expect(within(confirm).getByText(/확정하면 되돌릴 수 없습니다/)).toBeInTheDocument();
    await userEvent.click(within(confirm).getByRole('button', { name: '취소' }));
    expect(screen.queryByRole('group', { name: '대사 확정 확인' })).not.toBeInTheDocument();
    expect(screen.getByText(/^승인 결과 확인 중/)).toBeInTheDocument();
  });

  it('실패로 확정하면 결제실패가 되고 근거와 처리자가 조치 이력에 남는다', async () => {
    await signInAs('finance');
    await open(6);
    await userEvent.click(within(form()).getByRole('radio', { name: '실패' }));
    await userEvent.type(within(form()).getByLabelText(/^확인 근거/), 'PG 관리자 화면에서 실패 확인');
    await userEvent.click(within(form()).getByRole('button', { name: '대사 결과 저장' }));
    await userEvent.click(within(screen.getByRole('group', { name: '대사 확정 확인' })).getByRole('button', { name: '확정' }));
    const history = (await rows('조치 이력')).map(cells);
    expect(history[0]!.slice(1)).toEqual(['수동 대사', '박정산', '실패 처리. 근거: PG 관리자 화면에서 실패 확인']);
    expect(screen.getByText(/^결제실패/)).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: '수동 대사' })).not.toBeInTheDocument();
  });

  it('성공으로 확정하면 승인번호가 이력에 남고 결제완료가 된다', async () => {
    await signInAs('finance');
    await open(2);
    await userEvent.click(within(form()).getByRole('radio', { name: '성공' }));
    await userEvent.type(within(form()).getByLabelText(/^PG 승인번호/), 'PG-20260907-77');
    await userEvent.type(within(form()).getByLabelText(/^확인 근거/), 'PG 관리자 화면에서 승인 확인');
    await userEvent.click(within(form()).getByRole('button', { name: '대사 결과 저장' }));
    await userEvent.click(within(screen.getByRole('group', { name: '대사 확정 확인' })).getByRole('button', { name: '확정' }));
    expect(await screen.findByText('성공 처리(승인번호 PG-20260907-77). 근거: PG 관리자 화면에서 승인 확인')).toBeInTheDocument();
    expect(screen.getByText(/^결제완료/)).toBeInTheDocument();
  });

  it('근거가 너무 짧으면 서버 오류를 근거 항목 아래에 보이고 확정 확인이 닫힌다', async () => {
    await signInAs('finance');
    await open(6);
    await userEvent.click(within(form()).getByRole('radio', { name: '실패' }));
    await userEvent.type(within(form()).getByLabelText(/^확인 근거/), '확인');
    await userEvent.click(within(form()).getByRole('button', { name: '대사 결과 저장' }));
    await userEvent.click(within(screen.getByRole('group', { name: '대사 확정 확인' })).getByRole('button', { name: '확정' }));
    expect(await screen.findByText('확인 근거를 5자 이상 입력해 주세요.')).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: '대사 확정 확인' })).not.toBeInTheDocument();
  });

  it('다른 곳에서 먼저 처리되었으면 안내한다', async () => {
    await signInAs('finance');
    await open(6);
    server.use(http.post('/api/admin/v1/transactions/:id/manual-reconcile', () => apiError('VERSION_CONFLICT')));
    await userEvent.click(within(form()).getByRole('radio', { name: '실패' }));
    await userEvent.type(within(form()).getByLabelText(/^확인 근거/), 'PG 관리자 화면에서 실패 확인');
    await userEvent.click(within(form()).getByRole('button', { name: '대사 결과 저장' }));
    await userEvent.click(within(screen.getByRole('group', { name: '대사 확정 확인' })).getByRole('button', { name: '확정' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('다른 곳에서 먼저 처리되었습니다.');
  });

  it('조치 권한이 없으면 조치 영역이 없다', async () => {
    await signInAs('group');
    server.use(
      http.get('/api/admin/v1/transactions/:id', () =>
        Response.json({
          transactionId: TXN(2), orderNo: 'ORD-20260907-000002', applicationNo: 'A20264-000203', amount: 60000, method: 'CARD', status: 'PENDING',
          requestedAt: '2026-09-07T10:01:12+09:00', approvedAt: null, recheckCount: 3, hasConflict: false, applicationId: '1', courseName: '초급컴퓨터',
          applicantName: '박○○', applicationState: 'PAYMENT_UNKNOWN', merchantId: 'MID', paymentDeadlineAt: null, recheckMax: 3, lastRecheckAt: null,
          notices: [], actions: [], refund: null, canRecheck: false, canReconcile: false, version: 1,
        }),
      ),
    );
    await open(2);
    expect(screen.queryByRole('button', { name: 'PG 재조회' })).not.toBeInTheDocument();
    expect(screen.queryByRole('form', { name: '수동 대사' })).not.toBeInTheDocument();
  });
});