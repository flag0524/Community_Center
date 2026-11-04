// 관리자 로그인 화면의 입력 검증, 오류 안내, 성공 뒤 이동, 이미 로그인한 경우를 확인하는 시험
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DEMO_ADMINS } from '../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../test/render';

useMockServer();

const fill = async (loginId: string, password: string) => {
  const form = await screen.findByRole('form', { name: '관리자 로그인' });
  if (loginId) await userEvent.type(screen.getByLabelText('아이디'), loginId);
  if (password) await userEvent.type(screen.getByLabelText('비밀번호'), password);
  return form;
};

describe('관리자 로그인', () => {
  it('로그인하지 않고 업무 화면을 열면 돌아올 주소를 남기고 로그인으로 간다', async () => {
    const { router } = renderApp('/pay/refunds');
    expect(await screen.findByRole('heading', { level: 1, name: '관리자 로그인' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
    expect(router.state.location.search).toBe('?next=%2Fpay%2Frefunds');
  });

  it('아이디나 비밀번호가 비어 있으면 요청 없이 항목별로 알려 준다', async () => {
    const requested: string[] = [];
    server.events.on('request:start', ({ request }) => requested.push(new URL(request.url).pathname));
    renderApp('/login');
    await fill('', '');
    await userEvent.click(screen.getByRole('button', { name: '로그인' }));
    server.events.removeAllListeners();
    expect(requested.filter((path) => path.endsWith('/auth/login'))).toEqual([]);
    expect(screen.getByText('아이디를 입력해 주세요.')).toBeInTheDocument();
    expect(screen.getByText('비밀번호를 입력해 주세요.')).toBeInTheDocument();
    expect(screen.getByLabelText('아이디')).toHaveAttribute('aria-invalid', 'true');
  });

  it('틀린 비밀번호는 서버 문구로 알리고 입력한 아이디는 남긴다', async () => {
    renderApp('/login');
    await fill(DEMO_ADMINS.group.loginId, 'wrong-password');
    await userEvent.click(screen.getByRole('button', { name: '로그인' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('아이디 또는 비밀번호를 확인해 주세요.');
    expect(screen.getByLabelText('아이디')).toHaveValue(DEMO_ADMINS.group.loginId);
  });

  it('실패가 이어지면 잠김 안내가 나온다', async () => {
    renderApp('/login');
    await fill(DEMO_ADMINS.group.loginId, 'wrong-password');
    for (let attempt = 0; attempt < 6; attempt += 1) {
      await userEvent.click(screen.getByRole('button', { name: '로그인' }));
      await waitFor(() => expect(screen.getByRole('button', { name: '로그인' })).toBeEnabled());
    }
    expect(screen.getByRole('alert')).toHaveTextContent('로그인 시도가 많아 잠시 이용할 수 없습니다.');
  });

  it('로그인하면 돌아올 주소의 화면으로 간다', async () => {
    const { router } = renderApp('/login?next=%2Fpay%2Frefunds');
    await fill(DEMO_ADMINS.group.loginId, DEMO_ADMINS.group.password);
    await userEvent.click(screen.getByRole('button', { name: '로그인' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/pay/refunds'));
    expect(await screen.findByRole('heading', { level: 1, name: '환불 검토' })).toBeInTheDocument();
  });

  it('돌아올 주소가 바깥 사이트이면 무시하고 처음 화면으로 간다', async () => {
    const { router } = renderApp('/login?next=%2F%2Fevil.example');
    await fill(DEMO_ADMINS.group.loginId, DEMO_ADMINS.group.password);
    await userEvent.click(screen.getByRole('button', { name: '로그인' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/dashboard'));
  });

  it('이미 로그인한 상태로 로그인 화면을 열면 업무 화면으로 간다', async () => {
    await signInAs('group');
    const { router } = renderApp('/login');
    await waitFor(() => expect(router.state.location.pathname).toBe('/dashboard'));
  });

  it('세션이 만료되어 왔다면 그 사실을 알려 준다', async () => {
    renderApp('/login?expired=1');
    expect(await screen.findByRole('status')).toHaveTextContent('오래 사용하지 않아 로그아웃되었습니다.');
  });
});