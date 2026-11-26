// 강사 출석 입력 화면(담당 강좌·회차 선택, 합계, 확인 뒤 저장, 명단 변경 안내, 메뉴 노출)을 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { login } from '../../api/auth';
import { DEMO, DEMO_INSTRUCTOR } from '../../mocks/auth';
import { MOCK_ROSTER_CHANGED, addMockStudent } from '../../mocks/teaching';
import { renderApp, server, signInAsDemo, useMockServer } from '../../test/render';

useMockServer();

const user = () => userEvent.setup({ delay: null });
const signInAsInstructor = () => login({ loginId: DEMO_INSTRUCTOR.loginId, password: DEMO.password });
const menu = () => screen.getByRole('navigation', { name: '마이페이지 하위 메뉴' });

async function open() {
  await signInAsInstructor();
  const view = renderApp('/teach/attendance');
  await screen.findByRole('table', { name: '출석 명단' });
  return view;
}

const choose = (name: string, mark: '출석' | '결석' | '미체크') =>
  user().click(screen.getByRole('radio', { name: new RegExp(`^${name.replace('*', '\\*')} \\d+ ${mark}$`) }));
const confirm = () => user().click(screen.getByRole('checkbox', { name: '입력 내용을 확인했습니다' }));
const save = () => user().click(screen.getByRole('button', { name: '저장' }));

describe('강사 출석 입력', () => {
  it('로그인하지 않으면 로그인으로 보낸다', async () => {
    const { router } = renderApp('/teach/attendance');
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
  });

  it('담당 강좌가 없으면 안내하고 메뉴에 보이지 않는다', async () => {
    await signInAsDemo();
    renderApp('/teach/attendance');
    expect(await screen.findByRole('heading', { name: '담당 강좌가 없습니다.' })).toBeInTheDocument();
    expect(within(menu()).queryByRole('link', { name: /강의 출석 입력/ })).not.toBeInTheDocument();
  });

  it('최근 수업 회차의 명단을 가린 이름과 신청번호로 보이고 연락처는 없다', async () => {
    await open();
    expect(screen.getByRole('heading', { level: 1, name: '강의 출석 입력' })).toBeInTheDocument();
    expect(within(menu()).getByRole('link', { name: /강의 출석 입력/ })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('combobox', { name: '담당 강좌' })).toHaveDisplayValue('건강요가 초급');
    expect(screen.getByRole('combobox', { name: '수업일' })).toHaveDisplayValue(/11\.09.*1회차 10:00.*미입력/);
    expect(screen.getByText('홍*동')).toBeInTheDocument();
    expect(screen.getByText('2000000000000000000013')).toBeInTheDocument();
    expect(screen.getByText('합계 출석 0 · 결석 0 · 미체크 3')).toBeInTheDocument();
    expect(screen.queryByText(/010-/)).not.toBeInTheDocument();
  });

  it('고른 대로 합계를 바꾸고 확인하기 전에는 저장할 수 없으며 저장하면 상태가 바뀐다', async () => {
    await open();
    await choose('김*수', '출석');
    await choose('이*희', '결석');
    expect(screen.getByText('합계 출석 1 · 결석 1 · 미체크 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
    await confirm();
    await save();
    expect(await screen.findByText('출석을 저장했습니다.')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('combobox', { name: '수업일' })).toHaveDisplayValue(/입력중/));
    expect(screen.getByRole('checkbox', { name: '입력 내용을 확인했습니다' })).not.toBeChecked();

    await choose('홍*동', '출석');
    await confirm();
    await save();
    await waitFor(() => expect(screen.getByRole('combobox', { name: '수업일' })).toHaveDisplayValue(/완료/));
    expect(screen.getByText('합계 출석 2 · 결석 1 · 미체크 0')).toBeInTheDocument();
  });

  it('수업일을 바꾸면 그 회차의 명단을 보이고 보강임을 알린다', async () => {
    const { router } = await open();
    await choose('김*수', '출석');
    await user().selectOptions(screen.getByRole('combobox', { name: '수업일' }), screen.getByRole('option', { name: /11\.04.*보강/ }));
    await waitFor(() => expect(router.state.location.search).toContain('lesson='));
    expect(await screen.findByText('합계 출석 0 · 결석 0 · 미체크 3')).toBeInTheDocument();
  });

  it('입력하는 사이에 명단이 바뀌면 알리고 다시 불러오면 새 수강생이 보인다', async () => {
    await open();
    addMockStudent('2000000000000000000014', '박*수');
    await choose('김*수', '출석');
    await confirm();
    await save();
    expect(await screen.findByText(MOCK_ROSTER_CHANGED)).toBeInTheDocument();
    await user().click(screen.getByRole('button', { name: '다시 불러오기' }));
    expect(await screen.findByText('박*수')).toBeInTheDocument();
    expect(screen.queryByText(MOCK_ROSTER_CHANGED)).not.toBeInTheDocument();
  });

  it('저장 요청에 멱등키를 싣고 확인 값과 명단 전체를 보낸다', async () => {
    const seen: Array<{ key: string | null; body: { confirmed: boolean; marks: unknown[] } }> = [];
    const listener = async ({ request }: { request: Request }) => {
      if (request.method === 'POST' && new URL(request.url).pathname === '/api/v1/me/teaching/attendance') {
        seen.push({ key: request.headers.get('Idempotency-Key'), body: await request.clone().json() });
      }
    };
    server.events.on('request:start', listener);
    try {
      await open();
      await confirm();
      await save();
      await screen.findByText('출석을 저장했습니다.');
    } finally {
      server.events.removeListener('request:start', listener);
    }
    expect(seen).toHaveLength(1);
    expect(seen[0]!.key).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(seen[0]!.body.confirmed).toBe(true);
    expect(seen[0]!.body.marks).toHaveLength(3);
  });
});

describe('상단 메뉴의 강의 출석 입력', () => {
  const link = { name: '강의 출석 입력' };
  const primary = () => screen.getByRole('navigation', { name: '주 메뉴' });
  const allMenu = () => within(document.getElementById('all-menu') as HTMLElement);

  it('담당 강좌가 있는 강사에게는 어느 화면의 주 메뉴와 전체 메뉴에도 보이고 눌러서 들어간다', async () => {
    await signInAsInstructor();
    const { router } = renderApp('/');
    await waitFor(() => expect(within(primary()).getByRole('link', link)).toHaveAttribute('href', '/teach/attendance'));
    expect(allMenu().getByRole('link', { ...link, hidden: true })).toHaveAttribute('href', '/teach/attendance');

    await user().click(within(primary()).getByRole('link', link));
    await screen.findByRole('table', { name: '출석 명단' });
    expect(router.state.location.pathname).toBe('/teach/attendance');
    // 마이페이지 묶음이 현재 위치로 표시된다
    expect(within(primary()).getByRole('link', { name: '마이페이지' }).parentElement).toHaveClass('active');
  });

  it('담당 강좌가 없는 회원에게는 보이지 않는다', async () => {
    await signInAsDemo();
    renderApp('/me/applications');
    await screen.findByRole('navigation', { name: '마이페이지 하위 메뉴' });
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(screen.queryByRole('link', { ...link, hidden: true })).not.toBeInTheDocument();
  });

  it('로그인하지 않았으면 담당 강좌를 묻지 않고 보이지 않는다', async () => {
    const asked: string[] = [];
    const listener = ({ request }: { request: Request }) => {
      asked.push(new URL(request.url).pathname);
    };
    server.events.on('request:start', listener);
    try {
      renderApp('/');
      await screen.findByRole('navigation', { name: '주 메뉴' });
      await waitFor(() => expect(asked).toContain('/api/v1/auth/session'));
      await new Promise((resolve) => setTimeout(resolve, 100));
    } finally {
      server.events.removeListener('request:start', listener);
    }
    expect(asked).not.toContain('/api/v1/me/teaching/courses');
    expect(screen.queryByRole('link', { ...link, hidden: true })).not.toBeInTheDocument();
  });

  it('로그아웃하면 메뉴에서 사라진다', async () => {
    await signInAsInstructor();
    renderApp('/');
    await waitFor(() => expect(within(primary()).getByRole('link', link)).toBeInTheDocument());
    await user().click(screen.getByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(screen.queryByRole('link', { ...link, hidden: true })).not.toBeInTheDocument());
  });
});
