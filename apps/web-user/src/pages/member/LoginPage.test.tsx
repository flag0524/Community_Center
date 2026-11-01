// 로그인 화면과 머리글의 로그인 상태 표시, 로그아웃 동작을 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DEMO } from '../../mocks/auth';
import { renderApp, useMockServer } from '../../test/render';

useMockServer();

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, loginId: string, password: string) {
  const form = await screen.findByRole('form', { name: '로그인' });
  const id = within(form).getByLabelText('아이디');
  const pw = within(form).getByLabelText('비밀번호');
  if (loginId) await user.type(id, loginId);
  if (password) await user.type(pw, password);
  await user.click(within(form).getByRole('button', { name: '로그인' }));
}

// 본문의 service-page-heading도 header 요소라 banner 역할이 둘이 된다. 사이트 머리글만 집는다.
// 로그인한 뒤 홈 화면이 실제로 그려질 때까지 기다린다. 로그인에 성공하면 로그인 화면은 폼 대신 이동 요소를 그리고,
// 라우터가 화면을 바꾸기 전에 다시 /login으로 이동하면 같은 요소가 재사용돼 되돌리는 동작이 다시 실행되지 않는다.
// 사람의 속도로는 일어나지 않는 시험 속 타이밍이다. 본문의 service-page 클래스는 로그인 라우트에만 붙는다.
async function signIn(user: ReturnType<typeof userEvent.setup>) {
  await fillAndSubmit(user, DEMO.loginId, DEMO.password);
  await waitFor(() => expect(screen.getByRole('main')).not.toHaveClass('service-page'));
}

const header = () => document.querySelector<HTMLElement>('header.header')!;

describe('로그인 화면 구성', () => {
  it('시안대로 제목, 현재 위치, 입력 칸, 계정 안내 링크를 둔다', async () => {
    renderApp('/login');

    expect(await screen.findByRole('heading', { level: 1, name: '로그인' })).toBeInTheDocument();
    const crumbs = screen.getByRole('navigation', { name: '현재 위치' });
    expect(within(crumbs).getByText('회원서비스')).toBeInTheDocument();
    expect(within(crumbs).getByText('로그인').tagName).toBe('STRONG');
    const form = screen.getByRole('form', { name: '로그인' });
    expect(within(form).getByLabelText('아이디')).toHaveAttribute('autocomplete', 'username');
    expect(within(form).getByLabelText('비밀번호')).toHaveAttribute('type', 'password');
    expect(within(form).getByLabelText('비밀번호')).toHaveAttribute('autocomplete', 'current-password');
    const links = screen.getByRole('navigation', { name: '계정 안내' });
    expect(within(links).getByRole('link', { name: '회원가입' })).toHaveAttribute('href', '/join');
    expect(within(links).getByRole('link', { name: '아이디 찾기' })).toHaveAttribute('href', '/find-id');
    expect(within(links).getByRole('link', { name: '비밀번호 찾기' })).toHaveAttribute('href', '/reset-password');
    expect(document.title).toBe('로그인 | 조리읍주민자치센터');
  });
});

describe('로그인', () => {
  it('성공하면 홈으로 가고 머리글에 이름과 로그아웃을 보인다', async () => {
    const user = userEvent.setup({ delay: null });
    const { router } = renderApp('/login');

    await fillAndSubmit(user, DEMO.loginId, DEMO.password);

    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(await within(header()).findByText('예시회원님')).toBeInTheDocument();
    expect(within(header()).getByRole('button', { name: '로그아웃' })).toBeInTheDocument();
    expect(within(header()).queryByRole('link', { name: '로그인' })).not.toBeInTheDocument();
  });

  it('next 주소가 사이트 안 경로이면 그곳으로 간다', async () => {
    const user = userEvent.setup({ delay: null });
    const { router } = renderApp('/login?next=%2Fcourses%2Fopen');

    await fillAndSubmit(user, DEMO.loginId, DEMO.password);

    await waitFor(() => expect(router.state.location.pathname).toBe('/courses/open'));
  });

  it.each(['//evil.example/x', 'https://evil.example/', '/\\evil.example', 'javascript:alert(1)'])(
    'next 주소가 사이트 밖을 가리키면(%s) 홈으로 보낸다',
    async (next) => {
      const user = userEvent.setup({ delay: null });
      const { router } = renderApp(`/login?next=${encodeURIComponent(next)}`);

      await fillAndSubmit(user, DEMO.loginId, DEMO.password);

      await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    },
  );

  it('아이디나 비밀번호가 틀리면 서버 문구를 알리고 로그인 화면에 머문다', async () => {
    const user = userEvent.setup({ delay: null });
    const { router } = renderApp('/login');

    await fillAndSubmit(user, DEMO.loginId, 'wrong-password');

    // 시안의 안내 문구 색(파랑)으로는 실패가 눈에 띄지 않아 오류 표시를 따로 단다.
    expect(await screen.findByText('아이디 또는 비밀번호를 확인해 주세요.')).toHaveClass('form-message', 'is-error');
    expect(router.state.location.pathname).toBe('/login');
    expect(within(header()).getByRole('link', { name: '로그인' })).toBeInTheDocument();
    // 비밀번호는 지우고 아이디는 남겨 다시 입력하기 쉽게 한다.
    expect(screen.getByLabelText('비밀번호')).toHaveValue('');
    expect(screen.getByLabelText('아이디')).toHaveValue(DEMO.loginId);
  });

  it('시도 횟수를 넘으면 잠금 문구를 알린다', async () => {
    const user = userEvent.setup({ delay: null });
    renderApp('/login');

    for (let attempt = 0; attempt < 5; attempt += 1) {
      await fillAndSubmit(user, attempt === 0 ? DEMO.loginId : '', 'wrong-password');
      await screen.findByText('아이디 또는 비밀번호를 확인해 주세요.');
    }
    await user.type(screen.getByLabelText('비밀번호'), DEMO.password);
    await user.click(screen.getByRole('button', { name: '로그인' }));

    expect(await screen.findByText('로그인 시도가 많아 잠시 이용할 수 없습니다.')).toBeInTheDocument();
  });

  it('비어 있는 칸은 서버에 묻지 않고 칸마다 안내한다', async () => {
    const user = userEvent.setup({ delay: null });
    renderApp('/login');

    await fillAndSubmit(user, '', '');

    const id = screen.getByLabelText('아이디');
    expect(id).toHaveAccessibleDescription('아이디를 입력해 주세요.');
    expect(id).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('비밀번호')).toHaveAccessibleDescription('비밀번호를 입력해 주세요.');
    expect(within(header()).getByRole('link', { name: '로그인' })).toBeInTheDocument();
  });

  it('이미 로그인한 상태로 로그인 화면을 열면 홈으로 보낸다', async () => {
    const user = userEvent.setup({ delay: null });
    const { router } = renderApp('/login');
    await signIn(user);

    await router.navigate('/login');

    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
  });
});

describe('로그아웃', () => {
  it('누르면 머리글이 로그인 링크로 돌아오고 새 로그인이 된다', async () => {
    const user = userEvent.setup({ delay: null });
    const { router } = renderApp('/login');
    await signIn(user);
    await user.click(await within(header()).findByRole('button', { name: '로그아웃' }));

    expect(await within(header()).findByRole('link', { name: '로그인' })).toBeInTheDocument();
    expect(within(header()).queryByText('예시회원님')).not.toBeInTheDocument();

    // 서버가 바꾼 토큰을 다시 받아 두 번째 로그인도 통과해야 한다.
    await router.navigate('/login');
    await fillAndSubmit(user, DEMO.loginId, DEMO.password);
    expect(await within(header()).findByText('예시회원님')).toBeInTheDocument();
  });
});
