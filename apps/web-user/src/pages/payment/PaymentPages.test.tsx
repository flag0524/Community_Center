// 결제 화면과 결제 결과 4종(성공·실패·결과 확인 중·기한 만료)이 서버 판정대로 그려지고 요청이 한 번만 나가는지 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createApplication } from '../../api/applications';
import { setMockNow } from '../../mocks/clock';
import { setMockPayOutcome } from '../../mocks/payOutcome';
import { renderApp, server, signInAsDemo, useMockServer } from '../../test/render';

useMockServer();

const DURING = new Date('2026-09-08T10:00:00+09:00'); // 접수 기간
const PAID_COURSE = '1'; // 초급컴퓨터 60,000원

beforeEach(() => setMockNow(DURING));
afterEach(() => {
  setMockNow(null);
  setMockPayOutcome(null);
});

const user = () => userEvent.setup({ delay: null });
const definition = (term: string) => screen.getByText(term, { selector: 'dt' }).nextElementSibling as HTMLElement;

/** 로그인하고 유료 강좌를 신청해 결제 대기 신청을 만든 뒤 그 번호를 돌려준다. */
async function dueApplication(): Promise<string> {
  await signInAsDemo();
  const application = await createApplication(PAID_COURSE, crypto.randomUUID());
  return application.applicationId;
}

async function pay(id: string) {
  const view = renderApp(`/payment/${id}`);
  await user().click(await screen.findByRole('button', { name: '결제하기' }));
  return view;
}

describe('결제 화면', () => {
  it('로그인하지 않았으면 로그인으로 보낸다', async () => {
    const { router } = renderApp('/payment/2000000000000000000001');
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
  });

  it('결제 내역, 결제수단 선택, 남은 결제시간을 보이고 카드가 기본 선택이다', async () => {
    const id = await dueApplication();
    renderApp(`/payment/${id}`);

    expect(await screen.findByRole('heading', { level: 1, name: '수강료 결제' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: '결제수단' })).toBeInTheDocument();
    const methods = screen.getByRole('group', { name: '결제수단 선택' });
    expect(within(methods).getByRole('radio', { name: '신용·체크카드' })).toBeChecked();
    expect(within(methods).getByRole('radio', { name: '실시간 계좌이체' })).not.toBeChecked();
    expect(within(methods).queryByRole('radio', { name: /가상계좌/ })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: '결제 내역' })).toBeInTheDocument();
    expect(definition('강좌명')).toHaveTextContent('초급컴퓨터');
    expect(definition('수강료')).toHaveTextContent('60,000원');
    expect(definition('신청번호')).toHaveTextContent(id);
    expect(screen.getByRole('timer')).toHaveTextContent(/^남은 결제시간 (10:00|09:5\d)$/);
    expect(screen.getByRole('link', { name: '신청 상세' })).toHaveAttribute('href', `/me/applications/${id}`);
    expect(document.title).toBe('수강료 결제 | 조리읍주민자치센터');
  });

  it('결제기한이 이미 지난 신청은 결제 화면 대신 기한 만료 결과를 보인다', async () => {
    const id = await dueApplication();
    setMockNow(new Date(DURING.getTime() + 11 * 60 * 1000));
    const { router } = renderApp(`/payment/${id}`);

    expect(await screen.findByRole('heading', { level: 1, name: '결제기한 만료' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/payment/${id}/result`);
  });

  it('결제 요청에 결제수단과 멱등키를 싣고, 결제 승인 확인에는 서버가 정한 금액만 보내며, 눌러도 한 번만 보낸다', async () => {
    const id = await dueApplication();
    const seen: Array<{ path: string; key: string | null; body: unknown }> = [];
    const listener = async ({ request }: { request: Request }) => {
      const path = new URL(request.url).pathname;
      if (request.method === 'POST' && /\/payments/.test(path)) {
        seen.push({ path, key: request.headers.get('Idempotency-Key'), body: await request.clone().json() });
      }
    };
    server.events.on('request:start', listener);
    try {
      renderApp(`/payment/${id}`);
      const u = user();
      await u.click(await screen.findByRole('radio', { name: '실시간 계좌이체' }));
      await u.dblClick(screen.getByRole('button', { name: '결제하기' }));
      await screen.findByRole('heading', { level: 1, name: '결제 완료' });
    } finally {
      server.events.removeListener('request:start', listener);
    }

    expect(seen).toHaveLength(2);
    expect(seen[0]!.path).toBe(`/api/v1/me/applications/${id}/payments`);
    expect(seen[0]!.key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
    expect(seen[0]!.body).toEqual({ method: 'TRANSFER' });
    expect(seen[1]!.path).toBe('/api/v1/payments/confirm');
    expect(seen[1]!.body).toMatchObject({ amount: 60000, paymentKey: expect.any(String), orderNo: expect.any(String) });
  });
});

describe('결제 결과', () => {
  it('성공하면 결제 완료와 신청 상세·영수증·환불신청 링크를 보인다', async () => {
    const id = await dueApplication();
    const { router } = await pay(id);

    expect(await screen.findByRole('heading', { level: 1, name: '결제 완료' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/payment/${id}/result`);
    expect(screen.getByRole('heading', { level: 2, name: '결제 완료' })).toBeInTheDocument();
    expect(screen.getByText('수강료 결제가 완료되었습니다.')).toBeInTheDocument();
    expect(definition('강좌명')).toHaveTextContent('초급컴퓨터');
    expect(definition('신청자')).toHaveTextContent('예시회원');
    expect(screen.getByRole('link', { name: '신청 상세' })).toHaveAttribute('href', `/me/applications/${id}`);
    expect(screen.getByRole('link', { name: '영수증' })).toHaveAttribute('href', expect.stringMatching(/^\/me\/receipts\/[0-9]{22}$/));
    expect(screen.getByRole('link', { name: '환불신청' })).toHaveAttribute('href', `/me/applications/${id}/refund`);
  });

  it('이미 결제한 신청의 결제 화면을 열면 결제 완료를 보이고 다시 결제할 수 없다', async () => {
    const id = await dueApplication();
    const first = await pay(id);
    await screen.findByRole('heading', { level: 1, name: '결제 완료' });
    first.unmount();

    renderApp(`/payment/${id}`);

    expect(await screen.findByRole('heading', { level: 1, name: '결제 완료' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '결제하기' })).not.toBeInTheDocument();
  });

  it('실패하면 다시 결제할 수 있고 같은 결제 화면에서 이어서 결제한다', async () => {
    setMockPayOutcome('failed');
    const id = await dueApplication();
    await pay(id);

    expect(await screen.findByRole('heading', { level: 1, name: '결제 실패' })).toBeInTheDocument();
    expect(screen.getByText('결제를 완료하지 못했습니다. 기한이 남아 있으면 다시 결제하실 수 있습니다.')).toBeInTheDocument();
    const retry = screen.getByRole('link', { name: '다시 결제하기' });
    expect(retry).toHaveAttribute('href', `/payment/${id}`);

    setMockPayOutcome('success');
    const u = user();
    await u.click(retry);
    await u.click(await screen.findByRole('button', { name: '결제하기' }));
    expect(await screen.findByRole('heading', { level: 1, name: '결제 완료' })).toBeInTheDocument();
  });

  it('결과를 알 수 없으면 확인 중으로 알리고 재결제를 막는다', async () => {
    setMockPayOutcome('unknown');
    const id = await dueApplication();
    const first = await pay(id);

    expect(await screen.findByRole('heading', { level: 1, name: '결제 결과 확인 중' })).toBeInTheDocument();
    expect(screen.getByText('승인 결과를 확인하고 있습니다. 확인 전 재결제와 자리 반환이 중단됩니다.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '다시 결제하기' })).not.toBeInTheDocument();
    first.unmount();

    // 결제 화면을 다시 열어도 확인 중 결과로 돌려보낸다.
    renderApp(`/payment/${id}`);
    expect(await screen.findByRole('heading', { level: 1, name: '결제 결과 확인 중' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '결제하기' })).not.toBeInTheDocument();
  });

  it('승인 확인 때 기한이 지났다고 하면 기한 만료 결과와 다시 신청하기를 보인다', async () => {
    setMockPayOutcome('expired');
    const id = await dueApplication();
    await pay(id);

    expect(await screen.findByRole('heading', { level: 1, name: '결제기한 만료' })).toBeInTheDocument();
    expect(screen.getByText('결제기한이 지나 신청이 만료되었습니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '다시 신청하기' })).toHaveAttribute('href', `/apply/${PAID_COURSE}`);
    expect(screen.getByRole('link', { name: '신청내역' })).toHaveAttribute('href', '/me/applications');
    expect(screen.queryByRole('link', { name: '다시 결제하기' })).not.toBeInTheDocument();
  });

  it('결제 대기가 아닌 신청(대기 중 등)은 신청 상세로 보낸다', async () => {
    await signInAsDemo();
    const waiting = await createApplication('3', crypto.randomUUID());
    const { router } = renderApp(`/payment/${waiting.applicationId}`);

    await waitFor(() => expect(router.state.location.pathname).toBe(`/me/applications/${waiting.applicationId}`));
  });
});
