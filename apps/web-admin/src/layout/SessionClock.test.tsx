// 관리자 세션 남은 시간 표시, 만료 2분 전 연장 안내, 연장, 만료 시 로그인 이동을 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { setMockIdleSeconds, touchMockSession } from '../mocks/auth';
import { renderApp, signInAs, useMockServer } from '../test/render';

useMockServer();

describe('세션 시간', () => {
  it('남은 시간을 분:초로 보여 주고 안내 창은 아직 열지 않는다', async () => {
    await signInAs('group');
    renderApp('/dashboard');
    expect(await screen.findByText(/^세션 1[45]:\d\d$/)).toBeInTheDocument();
    expect(document.querySelector('.adm-session-dialog')).not.toHaveAttribute('open');
  });

  it('만료 2분 안으로 들어오면 안내 창을 열고 계속 사용을 누르면 연장되어 닫힌다', async () => {
    setMockIdleSeconds(121);
    await signInAs('group');
    renderApp('/dashboard');
    const dialog = await waitFor(() => {
      const element = document.querySelector('.adm-session-dialog');
      expect(element).toHaveAttribute('open');
      return element as HTMLElement;
    }, { timeout: 4000 });
    expect(within(dialog).getByRole('heading', { name: '계속 사용하시겠습니까?' })).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole('button', { name: '계속 사용' }));
    await waitFor(() => expect(dialog).not.toHaveAttribute('open'));
    expect(screen.getByText(/^세션 02:0[01]$/)).toBeInTheDocument();
  });

  it('안내 창은 상단 도구 모음 밖에 두고 열리면 계속 사용에 초점을 준다', async () => {
    setMockIdleSeconds(121);
    await signInAs('group');
    renderApp('/dashboard');
    const dialog = await waitFor(() => {
      const element = document.querySelector('.adm-session-dialog');
      expect(element).toHaveAttribute('open');
      return element as HTMLElement;
    }, { timeout: 4000 });
    // 도구 모음 안에 있으면 그 버튼 꾸밈(테두리·배경 없음)과 작은 글자가 창에 옮아온다
    expect(dialog.closest('.adm-top-tools')).toBeNull();
    expect(within(dialog).getByRole('button', { name: '계속 사용' })).toHaveFocus();
  });

  it('안내 창의 로그아웃 버튼은 로그인 화면으로 보낸다', async () => {
    setMockIdleSeconds(121);
    await signInAs('group');
    const { router } = renderApp('/dashboard');
    const dialog = await waitFor(() => {
      const element = document.querySelector('.adm-session-dialog');
      expect(element).toHaveAttribute('open');
      return element as HTMLElement;
    }, { timeout: 4000 });
    await userEvent.click(within(dialog).getByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
  });

  it('작업 중이라 서버가 세션을 늘렸으면 안내 창을 열지 않고 새 남은 시간을 보인다', async () => {
    setMockIdleSeconds(122);
    await signInAs('group');
    renderApp('/dashboard');
    await screen.findByText(/^세션 02:0[0-2]$/);
    touchMockSession(900);
    expect(await screen.findByText(/^세션 1[45]:\d\d$/, undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(document.querySelector('.adm-session-dialog')).not.toHaveAttribute('open');
  });

  it('화면의 시간이 다 되어도 서버 세션이 살아 있으면 로그인으로 보내지 않는다', async () => {
    setMockIdleSeconds(2);
    await signInAs('group');
    const { router } = renderApp('/dashboard');
    await screen.findByText(/^세션 00:0[0-2]$/);
    const visited: string[] = [];
    router.subscribe((state) => visited.push(state.location.pathname));
    touchMockSession(900);
    expect(await screen.findByText(/^세션 1[45]:\d\d$/, undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/dashboard');
    expect(visited).not.toContain('/login'); // 로그인 화면을 거쳐 되돌아오면 입력하던 양식이 사라진다
  });

  it('아무것도 하지 않아 시간이 다 되면 만료 안내와 함께 로그인으로 간다', async () => {
    setMockIdleSeconds(2);
    await signInAs('group');
    const { router } = renderApp('/dashboard');
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'), { timeout: 5000 });
    expect(router.state.location.search).toBe('?expired=1');
    expect(await screen.findByRole('status')).toHaveTextContent('오래 사용하지 않아 로그아웃되었습니다.');
  });
});