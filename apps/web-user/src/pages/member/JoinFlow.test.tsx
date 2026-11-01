// 회원가입 4단계(약관 → 본인확인 → 정보입력 → 완료)의 진행, 단계 보호, 입력 검증, 서버 오류 처리를 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DEMO } from '../../mocks/auth';
import { renderApp, server, useMockServer } from '../../test/render';

useMockServer();

type User = ReturnType<typeof userEvent.setup>;

const NEW_ID = 'new-member';
const NEW_PASSWORD = 'New-pass-1234';

// 시안의 이름·휴대전화 확인 목록(dl)
const confirmedInfo = () => within(screen.getByText('이름', { selector: 'dt' }).closest('dl')!);

async function acceptTerms(user: User) {
  await user.click(await screen.findByRole('checkbox', { name: '이용약관에 동의합니다. (필수)' }));
  await user.click(screen.getByRole('checkbox', { name: '개인정보 수집·이용 안내에 동의합니다. (필수)' }));
  await user.click(screen.getByRole('button', { name: '다음' }));
}

async function requestCode(user: User, name = '홍길동', phone = '010-1234-5678') {
  await user.type(await screen.findByLabelText('이름'), name);
  await user.type(screen.getByLabelText('휴대전화'), phone);
  await user.click(screen.getByRole('checkbox', { name: '본인확인 진행에 동의합니다.' }));
  await user.click(screen.getByRole('button', { name: '인증번호 받기' }));
}

async function verifyCode(user: User, code: string = DEMO.otpCode) {
  await user.type(await screen.findByLabelText('인증번호'), code);
  await user.click(screen.getByRole('button', { name: '본인확인' }));
}

async function reachInfo(user: User) {
  const view = renderApp('/join');
  await acceptTerms(user);
  await requestCode(user);
  await verifyCode(user);
  await screen.findByRole('heading', { level: 1, name: '회원가입 · 정보입력' });
  return view;
}

async function fillInfo(user: User, overrides: Partial<Record<'id' | 'pw' | 'confirm' | 'email', string>> = {}) {
  const values = { id: NEW_ID, pw: NEW_PASSWORD, confirm: NEW_PASSWORD, email: 'new@example.test', ...overrides };
  await user.type(screen.getByLabelText('아이디'), values.id);
  await user.type(screen.getByLabelText('비밀번호'), values.pw);
  await user.type(screen.getByLabelText('비밀번호 확인'), values.confirm);
  await user.type(screen.getByLabelText('이메일'), values.email);
}

describe('1단계 약관동의', () => {
  it('시안대로 필수 약관 둘과 약관 보기 링크를 보인다', async () => {
    renderApp('/join');

    expect(await screen.findByRole('heading', { level: 1, name: '회원가입 · 약관동의' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: '약관동의' })).toBeInTheDocument();
    const terms = screen.getByRole('link', { name: '이용약관 보기 (새 창)' });
    expect(terms).toHaveAttribute('href', '/terms/terms-of-use');
    expect(terms).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('link', { name: '개인정보 안내 보기 (새 창)' })).toHaveAttribute('href', '/terms/privacy-policy');
    expect(screen.getByRole('checkbox', { name: '이용약관에 동의합니다. (필수)' })).not.toBeChecked();
    expect(document.title).toBe('회원가입 · 약관동의 | 조리읍주민자치센터');
  });

  it('둘 다 동의하지 않으면 넘어가지 않고 안내한다', async () => {
    const user = userEvent.setup({ delay: null });
    const { router } = renderApp('/join');
    await user.click(await screen.findByRole('checkbox', { name: '이용약관에 동의합니다. (필수)' }));
    await user.click(screen.getByRole('button', { name: '다음' }));

    expect(await screen.findByText('필수 약관에 모두 동의해 주세요.')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/join');
  });

  it('둘 다 동의하면 본인확인 단계로 간다', async () => {
    const user = userEvent.setup({ delay: null });
    const { router } = renderApp('/join');
    await acceptTerms(user);

    await waitFor(() => expect(router.state.location.pathname).toBe('/join/verify'));
    expect(await screen.findByRole('heading', { level: 1, name: '회원가입 · 본인확인' })).toBeInTheDocument();
  });
});

describe('단계 보호', () => {
  it.each(['/join/verify', '/join/info'])('약관에 동의하지 않고 %s 를 열면 1단계로 돌려보낸다', async (path) => {
    const { router } = renderApp(path);
    await waitFor(() => expect(router.state.location.pathname).toBe('/join'));
  });

  it('본인확인 없이 정보입력을 열면 본인확인 단계로 돌려보낸다', async () => {
    const user = userEvent.setup({ delay: null });
    const { router } = renderApp('/join');
    await acceptTerms(user);
    await screen.findByRole('heading', { level: 1, name: '회원가입 · 본인확인' });

    await router.navigate('/join/info');

    await waitFor(() => expect(router.state.location.pathname).toBe('/join/verify'));
  });
});

describe('2단계 본인확인', () => {
  async function openVerify(user: User) {
    const view = renderApp('/join');
    await acceptTerms(user);
    await screen.findByRole('heading', { level: 1, name: '회원가입 · 본인확인' });
    return view;
  }

  it('이름·휴대전화·동의가 비어 있으면 서버에 묻지 않고 칸마다 안내한다', async () => {
    const user = userEvent.setup({ delay: null });
    await openVerify(user);

    await user.click(screen.getByRole('button', { name: '인증번호 받기' }));

    expect(screen.getByLabelText('이름')).toHaveAccessibleDescription('이름을 입력해 주세요.');
    expect(screen.getByLabelText('휴대전화')).toHaveAccessibleDescription('휴대전화 번호를 확인해 주세요. (예: 010-1234-5678)');
    expect(screen.getByText('본인확인 진행에 동의해 주세요.')).toBeInTheDocument();
    expect(screen.queryByLabelText('인증번호')).not.toBeInTheDocument();
  });

  it('인증번호를 받으면 입력 칸이 나타나고 이름·휴대전화는 확인용으로 바뀐다', async () => {
    const user = userEvent.setup({ delay: null });
    await openVerify(user);
    await requestCode(user);

    expect(await screen.findByLabelText('인증번호')).toHaveAttribute('inputmode', 'numeric');
    expect(screen.getByLabelText('인증번호')).toHaveAttribute('autocomplete', 'one-time-code');
    // 안내는 오류 표시를 달지 않는다.
    expect(screen.getByText('인증번호를 문자로 보냈습니다. 5분 안에 입력해 주세요.')).not.toHaveClass('is-error');
    expect(screen.queryByLabelText('이름')).not.toBeInTheDocument();
    const info = confirmedInfo();
    expect(info.getByText('홍길동')).toBeInTheDocument();
    expect(info.getByText('010-1234-5678')).toBeInTheDocument();
  });

  it('인증번호가 틀리면 남은 횟수를 알리고 다시 입력하게 한다', async () => {
    const user = userEvent.setup({ delay: null });
    await openVerify(user);
    await requestCode(user);
    await verifyCode(user, '000000');

    expect(await screen.findByText('인증번호가 올바르지 않습니다. 남은 횟수 4회')).toHaveClass('is-error');
    expect(screen.getByLabelText('인증번호')).toHaveValue('');
  });

  it('인증번호 형식이 6자리 숫자가 아니면 서버에 묻지 않고 안내한다', async () => {
    const user = userEvent.setup({ delay: null });
    await openVerify(user);
    await requestCode(user);
    await verifyCode(user, '12ab');

    expect(screen.getByLabelText('인증번호')).toHaveAccessibleDescription('인증번호 6자리를 입력해 주세요.');
  });

  it('횟수를 모두 틀리면 서버 문구를 알리고 처음부터 다시 받게 한다', async () => {
    const user = userEvent.setup({ delay: null });
    await openVerify(user);
    await requestCode(user);
    for (let attempt = 0; attempt < 5; attempt += 1) {
      await verifyCode(user, '000000');
      await screen.findByText(new RegExp(`남은 횟수 ${4 - attempt}회`));
    }
    await verifyCode(user, DEMO.otpCode);

    expect(await screen.findByText('인증번호가 올바르지 않습니다.')).toBeInTheDocument();
    // 요청을 처음부터 다시 하도록 이름·휴대전화 입력 단계로 돌아간다.
    expect(await screen.findByRole('button', { name: '인증번호 받기' })).toBeInTheDocument();
    expect(screen.getByLabelText('이름')).toHaveValue('홍길동');
  });

  it('너무 일찍 다시 받으려 하면 서버 문구를 알린다', async () => {
    const user = userEvent.setup({ delay: null });
    await openVerify(user);
    await requestCode(user);
    await user.click(await screen.findByRole('button', { name: '인증번호 다시 받기' }));

    expect(await screen.findByText('인증번호는 잠시 후 다시 요청할 수 있습니다.')).toBeInTheDocument();
    expect(screen.getByLabelText('인증번호')).toBeInTheDocument();
  });

  it('맞는 인증번호면 정보입력 단계로 간다', async () => {
    const user = userEvent.setup({ delay: null });
    const { router } = await reachInfo(user);
    expect(router.state.location.pathname).toBe('/join/info');
  });
});

describe('3단계 정보입력', () => {
  it('확인된 이름·휴대전화와 입력 칸, 비밀번호 규칙 안내를 보인다', async () => {
    const user = userEvent.setup({ delay: null });
    await reachInfo(user);

    const info = confirmedInfo();
    expect(info.getByText('홍길동')).toBeInTheDocument();
    expect(info.getByText('010-1234-5678')).toBeInTheDocument();
    expect(screen.getByLabelText('비밀번호')).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByLabelText('비밀번호')).toHaveAccessibleDescription('비밀번호는 10자 이상으로 입력해 주세요.');
    expect(screen.getByRole('checkbox', { name: '센터 소식 수신에 동의합니다. (선택)' })).not.toBeChecked();
  });

  it('비어 있거나 규칙에 맞지 않는 값은 서버에 묻지 않고 칸마다 안내한다', async () => {
    const user = userEvent.setup({ delay: null });
    await reachInfo(user);
    await fillInfo(user, { id: ' ', pw: 'short', confirm: 'different', email: 'not-an-email' });
    await user.click(screen.getByRole('button', { name: '회원가입' }));

    expect(screen.getByLabelText('아이디')).toHaveAccessibleDescription('아이디를 입력해 주세요.');
    expect(screen.getByLabelText('비밀번호')).toHaveAccessibleDescription(
      expect.stringContaining('비밀번호는 10자 이상으로 입력해 주세요.'),
    );
    expect(screen.getByLabelText('비밀번호 확인')).toHaveAccessibleDescription('비밀번호가 서로 다릅니다.');
    expect(screen.getByLabelText('이메일')).toHaveAccessibleDescription('이메일 주소 형식을 확인해 주세요.');
  });

  it('아이디 중복확인은 사용 가능 여부를 알리고 아이디를 고치면 결과를 지운다', async () => {
    const user = userEvent.setup({ delay: null });
    await reachInfo(user);
    await user.type(screen.getByLabelText('아이디'), DEMO.loginId);
    await user.click(screen.getByRole('button', { name: '중복확인' }));
    expect(await screen.findByText('이미 사용 중인 아이디입니다.')).toBeInTheDocument();

    await user.clear(screen.getByLabelText('아이디'));
    await user.type(screen.getByLabelText('아이디'), NEW_ID);
    expect(screen.queryByText('이미 사용 중인 아이디입니다.')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '중복확인' }));
    expect(await screen.findByText('사용할 수 있는 아이디입니다.')).toBeInTheDocument();
  });

  it('아이디를 비운 채 중복확인을 누르면 안내한다', async () => {
    const user = userEvent.setup({ delay: null });
    await reachInfo(user);
    await user.click(screen.getByRole('button', { name: '중복확인' }));
    expect(screen.getByLabelText('아이디')).toHaveAccessibleDescription('아이디를 입력해 주세요.');
  });

  it('중복확인을 하지 않았더라도 서버가 이미 있는 아이디로 거절하면 아이디 칸에 알린다', async () => {
    const user = userEvent.setup({ delay: null });
    await reachInfo(user);
    await fillInfo(user, { id: DEMO.loginId });
    await user.click(screen.getByRole('button', { name: '회원가입' }));

    expect(await screen.findByLabelText('아이디')).toHaveAccessibleDescription('이미 사용 중인 아이디입니다.');
  });

  it('가입에 성공하면 완료 화면으로 가고 그 계정으로 로그인할 수 있다', async () => {
    const user = userEvent.setup({ delay: null });
    const { router } = await reachInfo(user);
    await fillInfo(user);
    await user.click(screen.getByRole('checkbox', { name: '센터 소식 수신에 동의합니다. (선택)' }));
    await user.click(screen.getByRole('button', { name: '회원가입' }));

    expect(await screen.findByRole('heading', { level: 1, name: '회원가입 완료' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/join/complete');
    expect(screen.getByRole('heading', { level: 2, name: '회원가입이 완료되었습니다.' })).toBeInTheDocument();
    const main = within(screen.getByRole('main'));
    expect(main.getByRole('link', { name: '로그인' })).toHaveAttribute('href', '/login');
    expect(main.getByRole('link', { name: '강좌 목록' })).toHaveAttribute('href', '/courses');

    // 가입한 아이디와 비밀번호로 로그인되고, 다른 비밀번호는 거절된다.
    await router.navigate('/login');
    const form = await screen.findByRole('form', { name: '로그인' });
    await user.type(within(form).getByLabelText('아이디'), NEW_ID);
    await user.type(within(form).getByLabelText('비밀번호'), 'Other-pass-0000');
    await user.click(within(form).getByRole('button', { name: '로그인' }));
    expect(await screen.findByText('아이디 또는 비밀번호를 확인해 주세요.')).toBeInTheDocument();
    await user.type(within(form).getByLabelText('비밀번호'), NEW_PASSWORD);
    await user.click(within(form).getByRole('button', { name: '로그인' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(await screen.findByText('홍길동님')).toBeInTheDocument();
  });

  it.each([
    [false, '선택 동의를 하지 않으면 센터 소식 수신은 동의 안 함으로 보낸다'],
    [true, '선택 동의를 하면 센터 소식 수신도 동의로 보낸다'],
  ])('가입 요청에 확인된 본인확인 값과 약관 버전을 싣고 %s: %s', async (marketing) => {
    const user = userEvent.setup({ delay: null });
    let body: Record<string, unknown> | null = null;
    const listener = async ({ request }: { request: Request }) => {
      if (request.method === 'POST' && new URL(request.url).pathname === '/api/v1/join') {
        body = (await request.clone().json()) as Record<string, unknown>;
      }
    };
    server.events.on('request:start', listener);
    try {
      await reachInfo(user);
      await fillInfo(user);
      if (marketing) await user.click(screen.getByRole('checkbox', { name: '센터 소식 수신에 동의합니다. (선택)' }));
      await user.click(screen.getByRole('button', { name: '회원가입' }));
      await screen.findByRole('heading', { level: 1, name: '회원가입 완료' });
    } finally {
      server.events.removeListener('request:start', listener);
    }

    expect(body).toMatchObject({
      code: DEMO.otpCode,
      loginId: NEW_ID,
      password: NEW_PASSWORD,
      email: 'new@example.test',
      agreements: [
        { termType: 'TERMS_OF_USE', version: '2026-시험', agreed: true },
        { termType: 'PRIVACY_CONSENT', version: '2026-시험', agreed: true },
        { termType: 'MARKETING_CONSENT', version: '2026-시험', agreed: marketing },
      ],
    });
    expect(body).toHaveProperty('certRequestId', expect.stringMatching(/^[0-9]{22}$/));
  });

  it('가입을 마친 뒤에는 같은 본인확인 결과로 정보입력 화면에 다시 들어올 수 없다', async () => {
    const user = userEvent.setup({ delay: null });
    const { router } = await reachInfo(user);
    await fillInfo(user);
    await user.click(screen.getByRole('button', { name: '회원가입' }));
    await screen.findByRole('heading', { level: 1, name: '회원가입 완료' });

    await router.navigate('/join/info');

    await waitFor(() => expect(router.state.location.pathname).toBe('/join'));
  });
});

