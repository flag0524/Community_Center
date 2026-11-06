// 권한에 따른 메뉴 구성, 권한 없는 화면, 로그아웃, 전체 메뉴 같은 공통 레이아웃 동작을 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';
import { apiError } from '../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../test/render';

useMockServer();

const primaryNav = () => screen.findByRole('navigation', { name: '주요 업무' });
const labels = (nav: HTMLElement) => within(nav).getAllByRole('link').map((link) => link.textContent);

describe('메뉴는 권한 응답으로만 구성된다', () => {
  it('운영묶음 관리자는 다섯 묶음을 모두 본다', async () => {
    await signInAs('group');
    renderApp('/edu/courses');
    expect(labels(await primaryNav())).toEqual(['운영 현황', '교육 운영', '수강·정산', '회원·콘텐츠', '시스템']);
  });

  it('결제·환불 담당자는 교육 운영·회원·콘텐츠·시스템 묶음이 없다', async () => {
    await signInAs('finance');
    renderApp('/pay/refunds');
    expect(labels(await primaryNav())).toEqual(['운영 현황', '수강·정산']);
  });

  it('현재 경로가 속한 묶음만 현재 위치로 알리고 왼쪽에 그 묶음의 하위 메뉴를 보인다', async () => {
    await signInAs('group');
    renderApp('/pay/waitlist');
    const nav = await primaryNav();
    expect(within(nav).getByRole('link', { name: '수강·정산' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: '교육 운영' })).not.toHaveAttribute('aria-current');
    const side = screen.getByRole('navigation', { name: '수강·정산 하위 메뉴' });
    expect(labels(side)).toEqual(['수강신청', '대기·자리 배정', '결제·거래 대조', '환불 검토', '감면 검토', '감면 처리 이력']);
    expect(within(side).getByRole('link', { name: '대기·자리 배정' })).toHaveAttribute('aria-current', 'page');
  });

  it('로그인한 관리자의 이름과 역할을 보여 준다', async () => {
    await signInAs('finance');
    renderApp('/pay/refunds');
    expect(await screen.findByText('박정산 · 결제·환불 담당자')).toBeInTheDocument();
  });

  it('처음 화면은 보이는 첫 메뉴로 간다', async () => {
    await signInAs('course');
    const { router } = renderApp('/');
    await waitFor(() => expect(router.state.location.pathname).toBe('/dashboard'));
  });
});

describe('권한 응답이 거절되면', () => {
  it('세션이 끝난 것으로 보고 만료 안내와 함께 로그인으로 간다', async () => {
    await signInAs('group');
    server.use(http.get('/api/admin/v1/me/permissions', () => apiError('UNAUTHENTICATED')));
    const { router } = renderApp('/dashboard');
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
    expect(router.state.location.search).toBe('?expired=1');
  });
});

describe('권한 없는 화면과 없는 주소', () => {
  it('메뉴에 없는 알려진 화면은 권한 없음 안내를 보이고 내용을 그리지 않는다', async () => {
    await signInAs('finance');
    renderApp('/edu/courses');
    expect(await screen.findByRole('heading', { level: 1, name: '이용 권한이 없습니다' })).toBeInTheDocument();
    expect(screen.queryByText('이 화면은 다음 단계에서 제공됩니다.')).not.toBeInTheDocument();
  });

  it('권한이 있는 화면은 그 화면의 제목을 보인다', async () => {
    await signInAs('finance');
    renderApp('/pay/transactions');
    expect(await screen.findByRole('heading', { level: 1, name: '결제·거래 대조' })).toBeInTheDocument();
  });

  it('없는 주소는 찾을 수 없음 안내를 보인다', async () => {
    await signInAs('group');
    renderApp('/없는/경로');
    expect(await screen.findByRole('heading', { level: 1, name: '페이지를 찾을 수 없습니다' })).toBeInTheDocument();
  });
});

describe('전체 메뉴', () => {
  it('열면 권한이 있는 모든 항목을 묶음별로 보이고 항목을 누르면 이동하며 닫힌다', async () => {
    await signInAs('group');
    const { router } = renderApp('/dashboard');
    await userEvent.click(await screen.findByRole('button', { name: '전체 메뉴' }));
    const dialog = document.getElementById('admin-all-menu') as HTMLDialogElement;
    expect(dialog).toHaveAttribute('open');
    const tree = within(dialog).getByRole('navigation', { name: '전체 관리자 메뉴' });
    expect(within(tree).getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual([
      '운영 현황',
      '교육 운영',
      '수강·정산',
      '회원·콘텐츠',
      '시스템',
    ]);
    await userEvent.click(within(tree).getByRole('link', { name: '환불 검토' }));
    expect(router.state.location.pathname).toBe('/pay/refunds');
    expect(dialog).not.toHaveAttribute('open');
  });

  it('닫기 버튼으로 닫힌다', async () => {
    await signInAs('group');
    renderApp('/dashboard');
    await userEvent.click(await screen.findByRole('button', { name: '전체 메뉴' }));
    const dialog = document.getElementById('admin-all-menu') as HTMLDialogElement;
    await userEvent.click(within(dialog).getByRole('button', { name: '전체 메뉴 닫기' }));
    expect(dialog).not.toHaveAttribute('open');
  });
});

describe('좁은 화면의 메뉴', () => {
  it('메뉴 버튼이 하위 메뉴 영역의 열림 상태를 알리고 이동하면 닫힌다', async () => {
    await signInAs('group');
    renderApp('/dashboard');
    const toggle = await screen.findByRole('button', { name: '메뉴' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById('admin-navigation')).toHaveClass('open');
    await userEvent.click(within(screen.getByRole('navigation', { name: '운영 현황 하위 메뉴' })).getByRole('link', { name: '수요·연령·정산 통계' }));
    await waitFor(() => expect(toggle).toHaveAttribute('aria-expanded', 'false'));
  });
});

describe('로그아웃', () => {
  it('누르면 로그인 화면으로 가고 다시 업무 화면을 열 수 없다', async () => {
    await signInAs('group');
    const { router } = renderApp('/dashboard');
    await userEvent.click(await screen.findByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
    await router.navigate('/pay/refunds');
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
    expect(router.state.location.search).toBe('?next=%2Fpay%2Frefunds');
  });
});