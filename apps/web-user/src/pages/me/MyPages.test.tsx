// 내 신청 내역·상세·취소·영수증·환불 신청·환불 내역 화면이 서버 판정대로 그려지고 요청이 올바르게 나가는지 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApplication } from '../../api/applications';
import { confirmPayment, requestPayment } from '../../api/payments';
import { setMockNow } from '../../mocks/clock';
import { setMockPayOutcome } from '../../mocks/payOutcome';
import { renderApp, server, signInAsDemo, useMockServer } from '../../test/render';

useMockServer();

const DURING = new Date('2026-09-08T10:00:00+09:00'); // 접수 기간, 개강 전
const AFTER_START = new Date('2026-11-15T10:00:00+09:00'); // 개강 후 2개월째

beforeEach(() => setMockNow(DURING));
afterEach(() => {
  setMockNow(null);
  setMockPayOutcome(null);
});

const user = () => userEvent.setup({ delay: null });
const definition = (term: string) => screen.getByText(term, { selector: 'dt' }).nextElementSibling as HTMLElement;

const apply = (courseId: string) => createApplication(courseId, crypto.randomUUID());

/** 유료 강좌를 신청하고 결제까지 끝낸다. 결제 완료된 신청을 돌려준다. */
async function paidApplication() {
  const application = await apply('1');
  const request = await requestPayment(application.applicationId, 'CARD', crypto.randomUUID());
  await confirmPayment({ orderNo: request.orderNo, paymentKey: 'key', amount: request.amount });
  return application;
}

describe('내 신청 내역', () => {
  it('로그인하지 않았으면 로그인으로 보낸다', async () => {
    const { router } = renderApp('/me/applications');
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent('/me/applications')}`);
  });

  it('신청이 없으면 안내와 강좌 보기 링크를 보인다', async () => {
    await signInAsDemo();
    renderApp('/me/applications');

    expect(await screen.findByRole('heading', { level: 1, name: '수강신청내역' })).toBeInTheDocument();
    expect(screen.getByText('신청 내역이 없습니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '강좌 보기' })).toHaveAttribute('href', '/courses');
    expect(document.title).toBe('수강신청내역 | 조리읍주민자치센터');
  });

  it('신청 강좌, 신청·결제·환불 상태를 서버 판정대로 최신순으로 보인다', async () => {
    await signInAsDemo();
    await apply('5'); // 무료
    await apply('3'); // 대기
    const due = await apply('1'); // 결제 대기
    renderApp('/me/applications');

    const table = await screen.findByRole('table', { name: '수강신청내역' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(3);
    const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
    expect(cells(rows[0]!)).toEqual(['초급컴퓨터', '결제대기', '미결제', '-', '상세']);
    expect(cells(rows[1]!)).toEqual(['라인댄스 A', '대기 3번', '결제 전', '-', '상세']);
    expect(cells(rows[2]!)).toEqual(['한글문해교실', '등록완료', '결제 불필요', '-', '상세']);
    const detail = within(rows[0]!).getByRole('link', { name: '상세 (초급컴퓨터)' });
    expect(detail).toHaveAttribute('href', `/me/applications/${due.applicationId}`);
  });

  it('결제를 마치면 결제완료로, 환불을 접수하면 환불상태가 접수로 바뀐다', async () => {
    await signInAsDemo();
    const paid = await paidApplication();
    const first = renderApp('/me/applications');
    const row = async () => within(await screen.findByRole('table', { name: '수강신청내역' })).getAllByRole('row')[1]!;
    expect(within(await row()).getByText('결제완료')).toBeInTheDocument();
    first.unmount();

    await user().click((await renderRefundApply(paid.applicationId)).submit);
    await screen.findByRole('heading', { level: 1, name: '환불신청 내역' });
    renderApp('/me/applications');
    expect(within(await row()).getByText('접수')).toBeInTheDocument();
  });
});

describe('신청 상세', () => {
  it('결제 대기 신청은 결제하기와 신청 취소를 보이고 영수증·환불은 보이지 않는다', async () => {
    await signInAsDemo();
    const due = await apply('1');
    renderApp(`/me/applications/${due.applicationId}`);

    expect(await screen.findByRole('heading', { level: 1, name: '수강신청 상세' })).toBeInTheDocument();
    expect(definition('강좌명')).toHaveTextContent('초급컴퓨터');
    expect(definition('신청번호')).toHaveTextContent(due.applicationId);
    expect(definition('신청자')).toHaveTextContent('예시회원');
    expect(definition('신청상태')).toHaveTextContent('결제대기');
    expect(definition('환불상태')).toHaveTextContent('신청 전');
    expect(screen.getByRole('link', { name: '결제하기' })).toHaveAttribute('href', `/payment/${due.applicationId}`);
    expect(screen.getByRole('button', { name: '신청 취소' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '영수증' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '환불신청' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '목록' })).toHaveAttribute('href', '/me/applications');
  });

  it('결제를 마친 신청은 영수증과 환불신청을 보이고 신청 취소는 보이지 않는다', async () => {
    await signInAsDemo();
    const paid = await paidApplication();
    renderApp(`/me/applications/${paid.applicationId}`);

    expect(await screen.findByRole('link', { name: '영수증' })).toHaveAttribute('href', expect.stringMatching(/^\/me\/receipts\/[0-9]{22}$/));
    expect(screen.getByRole('link', { name: '환불신청' })).toHaveAttribute('href', `/me/applications/${paid.applicationId}/refund`);
    expect(definition('신청상태')).toHaveTextContent('등록완료');
    expect(screen.queryByRole('button', { name: '신청 취소' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '결제하기' })).not.toBeInTheDocument();
  });

  it('대기 신청은 대기순번을 보이고 결제하기를 보이지 않는다', async () => {
    await signInAsDemo();
    const waiting = await apply('3');
    renderApp(`/me/applications/${waiting.applicationId}`);

    expect(await screen.findByRole('heading', { level: 1, name: '수강신청 상세' })).toBeInTheDocument();
    expect(definition('신청상태')).toHaveTextContent('대기 3번');
    expect(screen.queryByRole('link', { name: '결제하기' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '신청 취소' })).toBeInTheDocument();
  });

  it('없는 신청 번호는 찾을 수 없음이다', async () => {
    await signInAsDemo();
    renderApp('/me/applications/9999999999999999999999');
    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });
});

describe('신청 취소', () => {
  it('확인 단계에서 돌아가기를 누르면 아무것도 취소하지 않는다', async () => {
    await signInAsDemo();
    const due = await apply('1');
    renderApp(`/me/applications/${due.applicationId}`);
    const u = user();
    await u.click(await screen.findByRole('button', { name: '신청 취소' }));

    const confirm = screen.getByRole('group', { name: '신청 취소 확인' });
    expect(within(confirm).getByText('이 신청을 취소할까요? 취소하면 배정된 자리가 반환됩니다.')).toBeInTheDocument();
    await u.click(within(confirm).getByRole('button', { name: '돌아가기' }));

    expect(screen.queryByRole('group', { name: '신청 취소 확인' })).not.toBeInTheDocument();
    expect(definition('신청상태')).toHaveTextContent('결제대기');
  });

  it('취소하기를 누르면 취소 결과를 보이고 신청 상태가 신청취소로 바뀐다', async () => {
    await signInAsDemo();
    const due = await apply('1');
    const { router } = renderApp(`/me/applications/${due.applicationId}`);
    const u = user();
    await u.click(await screen.findByRole('button', { name: '신청 취소' }));
    await u.click(within(screen.getByRole('group', { name: '신청 취소 확인' })).getByRole('button', { name: '취소하기' }));

    expect(await screen.findByRole('heading', { level: 1, name: '신청 취소 결과' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/me/applications/${due.applicationId}/cancelled`);
    expect(screen.getByRole('heading', { level: 2, name: '신청이 취소되었습니다.' })).toBeInTheDocument();
    expect(screen.getByText('미결제 신청이 취소되었습니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '다시 신청하기' })).toHaveAttribute('href', '/apply/1');
    expect(screen.getByRole('link', { name: '신청내역' })).toHaveAttribute('href', '/me/applications');

    await router.navigate(`/me/applications/${due.applicationId}`);
    expect(await screen.findByText('신청취소', { selector: 'dd' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '신청 취소' })).not.toBeInTheDocument();
  });

  it('취소하기를 연달아 눌러도 취소 요청은 한 번만 나간다', async () => {
    await signInAsDemo();
    const due = await apply('1');
    let calls = 0;
    const listener = ({ request }: { request: Request }) => {
      if (request.method === 'POST' && new URL(request.url).pathname.endsWith('/cancel')) calls += 1;
    };
    server.events.on('request:start', listener);
    try {
      renderApp(`/me/applications/${due.applicationId}`);
      const u = user();
      await u.click(await screen.findByRole('button', { name: '신청 취소' }));
      await u.dblClick(within(screen.getByRole('group', { name: '신청 취소 확인' })).getByRole('button', { name: '취소하기' }));
      await screen.findByRole('heading', { level: 1, name: '신청 취소 결과' });
    } finally {
      server.events.removeListener('request:start', listener);
    }
    expect(calls).toBe(1);
  });

  it('서버가 취소를 거절하면 문구를 알리고 화면에 머문다', async () => {    await signInAsDemo();
    const due = await apply('1');
    server.use(
      http.post('/api/v1/me/applications/:id/cancel', () =>
        HttpResponse.json(
          { code: 'APLY_CANCEL_NOT_ALLOWED', message: '현재 상태에서는 신청을 취소할 수 없습니다.', requestId: 'r' },
          { status: 422 },
        ),
      ),
    );
    const { router } = renderApp(`/me/applications/${due.applicationId}`);
    const u = user();
    await u.click(await screen.findByRole('button', { name: '신청 취소' }));
    await u.click(within(screen.getByRole('group', { name: '신청 취소 확인' })).getByRole('button', { name: '취소하기' }));

    expect(await screen.findByText('현재 상태에서는 신청을 취소할 수 없습니다.')).toHaveClass('is-error');
    expect(router.state.location.pathname).toBe(`/me/applications/${due.applicationId}`);
  });
});

describe('영수증', () => {
  it('결제 내역과 승인번호를 보이고 인쇄 버튼이 인쇄를 연다', async () => {
    await signInAsDemo();
    const paid = await paidApplication();
    const detail = renderApp(`/me/applications/${paid.applicationId}`);
    const link = await screen.findByRole('link', { name: '영수증' });
    const href = link.getAttribute('href')!;
    detail.unmount();

    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    renderApp(href);

    expect(await screen.findByRole('heading', { level: 1, name: '결제 영수증' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: '수강료 결제 내역' })).toBeInTheDocument();
    expect(definition('강좌명')).toHaveTextContent('초급컴퓨터');
    expect(definition('수강료')).toHaveTextContent('60,000원');
    expect(definition('결제수단')).toHaveTextContent('신용·체크카드');
    expect(definition('승인번호')).toHaveTextContent(/^MOCK-/);
    expect(definition('신청자')).toHaveTextContent('예시회원');
    expect(screen.getByRole('link', { name: '신청 상세' })).toHaveAttribute('href', `/me/applications/${paid.applicationId}`);
    await user().click(screen.getByRole('button', { name: '인쇄' }));
    expect(print).toHaveBeenCalledTimes(1);
    print.mockRestore();
  });

  it('결제가 끝나지 않은 결제 번호의 영수증은 찾을 수 없음이다', async () => {
    await signInAsDemo();
    const due = await apply('1');
    const request = await requestPayment(due.applicationId, 'CARD', crypto.randomUUID()); // 승인 확인 전
    renderApp(`/me/receipts/${request.paymentId}`);
    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });

  it('없는 결제 번호는 찾을 수 없음이다', async () => {    await signInAsDemo();
    renderApp('/me/receipts/9999999999999999999999');
    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });
});

/** 환불 신청 화면을 열고 제출 버튼을 돌려준다. */
async function renderRefundApply(applicationId: string) {
  renderApp(`/me/applications/${applicationId}/refund`);
  const submit = await screen.findByRole('button', { name: '환불신청' });
  return { submit };
}

describe('환불 신청', () => {
  it('개강 전이면 결제금액 전액을 환불 가능 금액으로 보이고 증빙·계좌는 묻지 않는다', async () => {
    await signInAsDemo();
    const paid = await paidApplication();
    renderApp(`/me/applications/${paid.applicationId}/refund`);

    expect(await screen.findByRole('heading', { level: 1, name: '환불 신청' })).toBeInTheDocument();
    expect(definition('결제금액')).toHaveTextContent('60,000원');
    expect(definition('환불 가능 금액')).toHaveTextContent('60,000원');
    expect(screen.getByText('개강 전이므로 결제한 수강료 전액을 반환합니다.')).toBeInTheDocument();
    expect(screen.getByLabelText('환불 사유')).toHaveValue('수강 일정 변경');
    expect(within(screen.getByLabelText('환불 사유')).getAllByRole('option').map((o) => o.textContent)).toEqual([
      '수강 일정 변경',
      '건강상 사유',
      '거주지 이전',
      '기타',
    ]);
    expect(screen.queryByLabelText('증빙서류')).not.toBeInTheDocument();
    expect(document.title).toBe('환불 신청 | 조리읍주민자치센터');
  });

  it('개강 후이면 당월 수강료를 뺀 금액과 산정 근거를 보인다', async () => {
    await signInAsDemo();
    const paid = await paidApplication();
    setMockNow(AFTER_START);
    renderApp(`/me/applications/${paid.applicationId}/refund`);

    expect(await screen.findByRole('heading', { level: 1, name: '환불 신청' })).toBeInTheDocument();
    expect(definition('환불 가능 금액')).toHaveTextContent('20,000원');
    expect(screen.getByText('개강 후에는 당월 수강료를 제외하고 반환합니다. (교육 3개월 중 2개월 경과, 월 수강료 20,000원)')).toBeInTheDocument();
  });

  it('사유와 상세 사유를 한 문장으로 합쳐 멱등키와 함께 보내고, 금액은 보내지 않는다', async () => {
    await signInAsDemo();
    const paid = await paidApplication();
    const seen: Array<{ key: string | null; body: unknown }> = [];
    const listener = async ({ request }: { request: Request }) => {
      if (request.method === 'POST' && new URL(request.url).pathname === '/api/v1/me/refunds') {
        seen.push({ key: request.headers.get('Idempotency-Key'), body: await request.clone().json() });
      }
    };
    server.events.on('request:start', listener);
    try {
      renderApp(`/me/applications/${paid.applicationId}/refund`);
      const u = user();
      await u.selectOptions(await screen.findByLabelText('환불 사유'), '건강상 사유');
      await u.type(screen.getByLabelText('상세 사유'), '무릎 수술');
      await u.dblClick(screen.getByRole('button', { name: '환불신청' }));
      await screen.findByRole('heading', { level: 1, name: '환불신청 내역' });
    } finally {
      server.events.removeListener('request:start', listener);
    }

    expect(seen).toHaveLength(1);
    expect(seen[0]!.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(seen[0]!.body).toEqual({ applicationId: paid.applicationId, reason: '건강상 사유 · 무릎 수술' });
  });

  it('접수하면 환불신청 내역에 접수 단계로 나타나고 같은 신청은 다시 신청할 수 없다', async () => {
    await signInAsDemo();
    const paid = await paidApplication();
    const { router } = renderApp(`/me/applications/${paid.applicationId}/refund`);
    await user().click(await screen.findByRole('button', { name: '환불신청' }));

    expect(await screen.findByRole('heading', { level: 1, name: '환불신청 내역' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/me/refunds');
    expect(screen.getByText('환불신청이 접수되었습니다.')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: '환불신청 내역' });
    expect(within(table).getAllByRole('row')[1]!.textContent).toContain('초급컴퓨터');
    expect(within(table).getAllByRole('row')[1]!.textContent).toContain('60,000원');
    expect(within(table).getAllByRole('row')[1]!.textContent).toContain('접수');

    await router.navigate(`/me/applications/${paid.applicationId}/refund`);
    expect(await screen.findByText('이미 환불을 접수했습니다. 처리 결과는 환불신청 내역에서 확인해 주세요.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '환불신청' })).not.toBeInTheDocument();
  });

  it('결제하지 않은 신청은 서버의 사유를 알리고 신청 양식을 보이지 않는다', async () => {
    await signInAsDemo();
    const due = await apply('1');
    renderApp(`/me/applications/${due.applicationId}/refund`);

    expect(await screen.findByText('환불을 신청할 수 없는 상태입니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '환불신청' })).not.toBeInTheDocument();
  });
});

describe('환불신청 내역', () => {
  it('환불 내역이 없으면 안내한다', async () => {
    await signInAsDemo();
    renderApp('/me/refunds');
    expect(await screen.findByText('환불신청 내역이 없습니다.')).toBeInTheDocument();
  });

  it.each([
    ['RECEIVED', '접수', null],
    ['PROCESSING', '처리 중', null],
    ['ON_HOLD', '보류', '증빙 확인이 필요합니다.'],
    ['DONE', '환불완료', null],
    ['REJECTED', '반려', '환불 대상이 아닙니다.'],
  ])('%s 단계는 %s로 보이고 보류·반려는 사유를 함께 보인다', async (stage, label, reason) => {
    await signInAsDemo();
    server.use(
      http.get('/api/v1/me/refunds', () =>
        HttpResponse.json({
          items: [
            {
              refundId: '4000000000000000000001',
              applicationId: '2000000000000000000001',
              courseName: '초급컴퓨터',
              amount: 60000,
              status: 'REQUESTED',
              stage,
              reason,
              requestedAt: '2026-09-08T10:00:00+09:00',
              completedAt: null,
            },
          ],
          page: 1,
          size: 10,
          total: 1,
          criteria: { basisAt: '2026-09-08T10:00:00+09:00', description: null },
        }),
      ),
    );
    renderApp('/me/refunds');

    const row = within(await screen.findByRole('table', { name: '환불신청 내역' })).getAllByRole('row')[1]!;
    expect(within(row).getByText(label)).toBeInTheDocument();
    if (reason) expect(within(row).getByText(reason)).toBeInTheDocument();
  });
});
