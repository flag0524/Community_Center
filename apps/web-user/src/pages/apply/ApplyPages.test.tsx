// 수강신청 화면과 접수 결과(결제 대기·무료 등록·대기신청) 화면이 서버 판정대로 그려지고 신청이 한 번만 전송되는지 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { join, login, logout, requestJoinOtp, verifyOtp } from '../../api/auth';
import { DEMO } from '../../mocks/auth';
import { setMockNow } from '../../mocks/clock';
import { renderApp, server, signInAsDemo, useMockServer } from '../../test/render';

useMockServer();

const DURING = new Date('2026-09-08T10:00:00+09:00'); // 접수 기간
const AFTER = new Date('2026-11-01T10:00:00+09:00'); // 접수 마감 뒤

const PAID = '1'; // 초급컴퓨터 60,000원
const FREE = '5'; // 한글문해교실 0원
const FULL = '3'; // 라인댄스 A, 모의 데이터에서 정원이 모두 찬 강좌

beforeEach(() => setMockNow(DURING));
afterEach(() => setMockNow(null));

const user = () => userEvent.setup({ delay: null });
const definition = (term: string) => screen.getByText(term, { selector: 'dt' }).nextElementSibling as HTMLElement;

async function apply(courseId: string) {
  await signInAsDemo();
  const view = renderApp(`/apply/${courseId}`);
  await user().click(await screen.findByRole('button', { name: /^(수강신청|대기신청)$/ }));
  return view;
}

describe('신청 화면', () => {
  it('로그인하지 않았으면 로그인으로 보내고 돌아올 주소를 남긴다', async () => {
    const { router } = renderApp(`/apply/${PAID}`);

    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent(`/apply/${PAID}`)}`);
  });

  it('강좌 정보와 서버가 산정한 금액, 결제 제한시간을 보이고 수강신청 버튼을 둔다', async () => {
    await signInAsDemo();
    renderApp(`/apply/${PAID}`);

    expect(await screen.findByRole('heading', { level: 1, name: '수강신청' })).toBeInTheDocument();
    const crumbs = screen.getByRole('navigation', { name: '현재 위치' });
    expect(within(crumbs).getByRole('link', { name: '초급컴퓨터' })).toHaveAttribute('href', `/courses/${PAID}`);
    expect(definition('강좌명')).toHaveTextContent('초급컴퓨터');
    expect(definition('강사')).toHaveTextContent('추순자');
    expect(definition('수강료')).toHaveTextContent('60,000원');
    expect(definition('감면')).toHaveTextContent('0원');
    expect(definition('결제금액')).toHaveTextContent('60,000원');
    expect(screen.getByText(/자리를 배정받으면 10분\(600초\) 안에 결제해야 합니다/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '수강신청' })).toBeEnabled();
    expect(document.title).toBe('수강신청 | 조리읍주민자치센터');
  });

  it('수강료가 0원인 강좌는 결제 제한시간 안내를 보이지 않는다', async () => {
    await signInAsDemo();
    renderApp(`/apply/${FREE}`);

    expect(await screen.findByRole('button', { name: '수강신청' })).toBeInTheDocument();
    expect(definition('결제금액')).toHaveTextContent('0원');
    expect(screen.queryByText(/안에 결제해야 합니다/)).not.toBeInTheDocument();
  });

  it('접수 기간이 아니면 서버의 사유를 알리고 신청 버튼을 두지 않는다', async () => {
    setMockNow(AFTER);
    await signInAsDemo();
    renderApp(`/apply/${PAID}`);

    expect(await screen.findByText('접수기간이 아닙니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '수강신청' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '강좌 상세' })).toHaveAttribute('href', `/courses/${PAID}`);
  });

  it('정원이 찬 강좌는 대기신청으로 안내한다', async () => {
    await signInAsDemo();
    renderApp(`/apply/${FULL}`);

    expect(await screen.findByRole('button', { name: '대기신청' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: '수강신청' })).not.toBeInTheDocument();
    expect(screen.getByText(/정원이 모두 찼습니다\. 대기신청을 하면 순번이 정해지고/)).toBeInTheDocument();
  });

  it('없는 강좌는 찾을 수 없음 화면을 보인다', async () => {
    await signInAsDemo();
    renderApp('/apply/999');
    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });
});

describe('신청과 접수 결과', () => {
  it('유료 강좌를 신청하면 결제 대기 결과를 보이고 결제하기 링크를 준다', async () => {
    const { router } = await apply(PAID);

    expect(await screen.findByRole('heading', { level: 1, name: '수강신청 접수' })).toBeInTheDocument();
    expect(router.state.location.pathname).toMatch(/^\/applications\/[0-9]{22}\/done$/);
    const id = router.state.location.pathname.split('/')[2]!;
    expect(screen.getByRole('heading', { level: 2, name: '수강신청이 접수되었습니다.' })).toBeInTheDocument();
    expect(screen.getByText('자리가 배정되었습니다. 결제기한 안에 수강료를 결제해 주세요.')).toBeInTheDocument();
    expect(definition('강좌명')).toHaveTextContent('초급컴퓨터');
    expect(definition('수강료')).toHaveTextContent('60,000원');
    expect(definition('신청번호')).toHaveTextContent(id);
    expect(definition('신청자')).toHaveTextContent('예시회원');
    expect(screen.getByRole('link', { name: '결제하기' })).toHaveAttribute('href', `/payment/${id}`);
    expect(screen.getByRole('link', { name: '신청 상세' })).toHaveAttribute('href', `/me/applications/${id}`);
  });

  it('수강료가 0원이면 결제 없이 등록 완료를 보인다', async () => {
    await apply(FREE);

    expect(await screen.findByRole('heading', { level: 1, name: '무료·전액감면 등록' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: '수강 등록이 완료되었습니다.' })).toBeInTheDocument();
    expect(screen.getByText('납부금액은 0원이며 별도 결제가 필요하지 않습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '결제하기' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '신청내역' })).toHaveAttribute('href', '/me/applications');
  });

  it('정원이 찬 강좌를 신청하면 대기순번을 알린다', async () => {
    await apply(FULL);

    expect(await screen.findByRole('heading', { level: 1, name: '대기신청 접수' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: '대기신청이 접수되었습니다.' })).toBeInTheDocument();
    expect(screen.getByText('대기순번 3번 · 자리가 배정되면 결제하실 수 있습니다.')).toBeInTheDocument();
    expect(
      screen.getByText(/취소·미결제 만료 시 다음 유효 대기자에게 자동 배정합니다\. 새 유료 자리 배정 시 10분의 결제기한이 시작됩니다\./),
    ).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '결제하기' })).not.toBeInTheDocument();
  });

  it('신청 요청에 멱등키를 싣고 금액은 보내지 않으며 버튼을 누르는 동안 다시 보내지 않는다', async () => {
    const seen: Array<{ key: string | null; body: unknown }> = [];
    const listener = async ({ request }: { request: Request }) => {
      if (request.method === 'POST' && new URL(request.url).pathname === '/api/v1/me/applications') {
        seen.push({ key: request.headers.get('Idempotency-Key'), body: await request.clone().json() });
      }
    };
    server.events.on('request:start', listener);
    try {
      await signInAsDemo();
      renderApp(`/apply/${PAID}`);
      const button = await screen.findByRole('button', { name: '수강신청' });
      const u = user();
      await u.dblClick(button);
      await screen.findByRole('heading', { level: 1, name: '수강신청 접수' });
    } finally {
      server.events.removeListener('request:start', listener);
    }

    expect(seen).toHaveLength(1);
    expect(seen[0]!.key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
    expect(seen[0]!.body).toEqual({ courseId: PAID });
  });

  it('이미 신청한 강좌의 신청 화면은 신청 버튼 대신 안내와 내 신청 링크를 보인다', async () => {
    const { router } = await apply(PAID);
    await screen.findByRole('heading', { level: 1, name: '수강신청 접수' });

    await router.navigate(`/apply/${PAID}`);

    expect(await screen.findByText('이미 신청한 강좌입니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '수강신청' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '신청내역' })).toHaveAttribute('href', '/me/applications');
  });

  it('다른 회원의 신청 번호로는 결과 화면을 열 수 없다(없는 번호와 같은 404)', async () => {
    const first = await apply(PAID);
    await screen.findByRole('heading', { level: 1, name: '수강신청 접수' });
    const mine = first.router.state.location.pathname.split('/')[2]!;
    first.unmount();

    // 다른 회원이 가입하고 로그인한 새 화면에서 연다(앞 회원의 화면 캐시와 무관해야 한다).
    await logout();
    const issued = await requestJoinOtp('01055556666', '다른회원');
    await verifyOtp(issued.certRequestId, DEMO.otpCode);
    await join({
      certRequestId: issued.certRequestId,
      code: DEMO.otpCode,
      loginId: 'other-member',
      password: 'Other-pass-1234',
      email: 'other@example.test',
      agreements: [{ termType: 'TERMS_OF_USE', version: '2026-시험', agreed: true }],
    });
    await login({ loginId: 'other-member', password: 'Other-pass-1234' });
    renderApp(`/applications/${mine}/done`);

    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });

  it('로그아웃하면 앞 회원의 신청 정보를 화면 캐시에서 지운다', async () => {
    const { router, queryClient } = await apply(PAID);
    await screen.findByRole('heading', { level: 1, name: '수강신청 접수' });
    const id = router.state.location.pathname.split('/')[2]!;
    expect(queryClient.getQueryData(['me', 'applications', id])).toBeDefined();

    const header = document.querySelector<HTMLElement>('header.header')!;
    await user().click(within(header).getByRole('button', { name: '로그아웃' }));

    await waitFor(() => expect(within(header).getByRole('link', { name: '로그인' })).toBeInTheDocument());
    expect(queryClient.getQueryData(['me', 'applications', id])).toBeUndefined();
    expect(queryClient.getQueriesData({ queryKey: ['me'] })).toEqual([]);
  });

  it('로그인하면 앞에 남은 회원 전용 캐시를 지운다', async () => {
    const { queryClient } = renderApp('/login');
    queryClient.setQueryData(['me', 'applications', 'stale'], { stale: true });

    const u = user();
    const form = await screen.findByRole('form', { name: '로그인' });
    await u.type(within(form).getByLabelText('아이디'), DEMO.loginId);
    await u.type(within(form).getByLabelText('비밀번호'), DEMO.password);
    await u.click(within(form).getByRole('button', { name: '로그인' }));

    await waitFor(() => expect(screen.getByRole('main')).not.toHaveClass('service-page'));
    expect(queryClient.getQueryData(['me', 'applications', 'stale'])).toBeUndefined();
  });

  it('남의 신청이거나 없는 신청 번호의 결과 화면은 찾을 수 없음이다', async () => {
    await signInAsDemo();
    renderApp('/applications/9999999999999999999999/done');
    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });
});
