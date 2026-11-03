// 아이디 찾기, 비밀번호 재설정, 회원정보수정, 비밀번호 변경, 회원탈퇴 화면의 흐름과 검증, 서버 오류 처리를 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createApplication } from '../../api/applications';
import { setMockNow } from '../../mocks/clock';
import { DEMO } from '../../mocks/auth';
import { renderApp, signInAsDemo, useMockServer } from '../../test/render';

useMockServer();

type User = ReturnType<typeof userEvent.setup>;
const user = () => userEvent.setup({ delay: null });
const definition = (term: string) => screen.getByText(term, { selector: 'dt' }).nextElementSibling as HTMLElement;
const DURING = new Date('2026-09-08T10:00:00+09:00');

beforeEach(() => setMockNow(DURING));
afterEach(() => setMockNow(null));

/** 이름·휴대전화로 인증번호를 받아 6자리를 확인한다. extra에는 비밀번호 재설정의 아이디를 넣는다. */
async function verifyIdentity(u: User, name = DEMO.member.name, phone = '010-0000-0000', loginId?: string) {
  if (loginId) await u.type(await screen.findByLabelText('아이디'), loginId);
  await u.type(await screen.findByLabelText('이름'), name);
  await u.type(screen.getByLabelText('휴대전화'), phone);
  await u.click(screen.getByRole('button', { name: '인증번호 받기' }));
  await u.type(await screen.findByLabelText('인증번호'), DEMO.otpCode);
  await u.click(screen.getByRole('button', { name: '본인확인' }));
}

describe('아이디 찾기', () => {
  it('본인확인을 마치면 앞 2글자만 보이는 아이디와 비밀번호 찾기 링크를 보인다', async () => {
    renderApp('/find-id');
    expect(await screen.findByRole('heading', { level: 1, name: '아이디 찾기' })).toBeInTheDocument();
    expect(document.title).toBe('아이디 찾기 | 조리읍주민자치센터');
    await verifyIdentity(user());

    expect(await screen.findByRole('heading', { level: 3, name: '가입한 아이디' })).toBeInTheDocument();
    expect(screen.getByText('de*********')).toBeInTheDocument();
    expect(screen.queryByText(DEMO.loginId)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '비밀번호 찾기' })).toHaveAttribute('href', '/reset-password');
    expect(within(screen.getByRole('main')).getByRole('link', { name: '로그인' })).toHaveAttribute('href', '/login');
  });

  it('일치하는 회원이 없으면 없다고만 알린다', async () => {
    renderApp('/find-id');
    await verifyIdentity(user(), '없는사람', '010-9999-9999');

    expect(await screen.findByText('일치하는 회원 정보를 찾지 못했습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 3, name: '가입한 아이디' })).not.toBeInTheDocument();
  });

  it('이름과 휴대전화가 비어 있으면 서버에 묻지 않고 칸마다 안내한다', async () => {
    renderApp('/find-id');
    await user().click(await screen.findByRole('button', { name: '인증번호 받기' }));

    expect(screen.getByLabelText('이름')).toHaveAccessibleDescription('이름을 입력해 주세요.');
    expect(screen.getByLabelText('휴대전화')).toHaveAccessibleDescription('휴대전화 번호를 확인해 주세요. (예: 010-1234-5678)');
  });

  it('인증번호가 틀리면 남은 횟수를 알린다', async () => {
    renderApp('/find-id');
    const u = user();
    await u.type(await screen.findByLabelText('이름'), DEMO.member.name);
    await u.type(screen.getByLabelText('휴대전화'), '010-0000-0000');
    await u.click(screen.getByRole('button', { name: '인증번호 받기' }));
    await u.type(await screen.findByLabelText('인증번호'), '000000');
    await u.click(screen.getByRole('button', { name: '본인확인' }));

    expect(await screen.findByText('인증번호가 올바르지 않습니다. 남은 횟수 4회')).toHaveClass('is-error');
  });
});

describe('비밀번호 재설정', () => {
  const NEW_PASSWORD = 'Brand-new-pass-1';

  async function resetTo(u: User, password: string, confirm = password) {
    await u.type(await screen.findByLabelText('새 비밀번호'), password);
    await u.type(screen.getByLabelText('새 비밀번호 확인'), confirm);
    await u.click(screen.getByRole('button', { name: '변경' }));
  }

  it('본인확인 뒤 새 비밀번호로 바꾸면 완료를 알리고 새 비밀번호로만 로그인된다', async () => {
    const view = renderApp('/reset-password');
    expect(await screen.findByRole('heading', { level: 1, name: '비밀번호 재설정' })).toBeInTheDocument();
    const u = user();
    await verifyIdentity(u, DEMO.member.name, '010-0000-0000', DEMO.loginId);
    expect(screen.queryByLabelText('아이디')).not.toBeInTheDocument();
    await resetTo(u, NEW_PASSWORD);

    expect(await screen.findByRole('heading', { level: 2, name: '비밀번호가 변경되었습니다.' })).toBeInTheDocument();
    const main = within(screen.getByRole('main'));
    expect(main.getByRole('link', { name: '로그인' })).toHaveAttribute('href', '/login');

    await view.router.navigate('/login');
    const form = await screen.findByRole('form', { name: '로그인' });
    await u.type(within(form).getByLabelText('아이디'), DEMO.loginId);
    await u.type(within(form).getByLabelText('비밀번호'), DEMO.password);
    await u.click(within(form).getByRole('button', { name: '로그인' }));
    expect(await screen.findByText('아이디 또는 비밀번호를 확인해 주세요.')).toBeInTheDocument();
    await u.type(within(form).getByLabelText('비밀번호'), NEW_PASSWORD);
    await u.click(within(form).getByRole('button', { name: '로그인' }));
    expect(await within(document.querySelector<HTMLElement>('header.header')!).findByText('예시회원님')).toBeInTheDocument();
  });

  it('새 비밀번호가 짧거나 서로 다르면 서버에 묻지 않고 안내한다', async () => {
    renderApp('/reset-password');
    const u = user();
    await verifyIdentity(u, DEMO.member.name, '010-0000-0000', DEMO.loginId);
    await resetTo(u, 'short', 'different');

    expect(screen.getByLabelText('새 비밀번호')).toHaveAccessibleDescription(expect.stringContaining('10자 이상'));
    expect(screen.getByLabelText('새 비밀번호 확인')).toHaveAccessibleDescription('비밀번호가 서로 다릅니다.');
  });

  it('아이디·이름·휴대전화가 일치하지 않으면 서버 문구를 알리고 완료로 넘어가지 않는다', async () => {
    renderApp('/reset-password');
    const u = user();
    await verifyIdentity(u, '다른이름', '010-0000-0000', DEMO.loginId);
    await resetTo(u, NEW_PASSWORD);

    expect(await screen.findByText('입력하신 정보와 일치하는 회원이 없습니다.')).toHaveClass('is-error');
    expect(screen.queryByRole('heading', { level: 2, name: '비밀번호가 변경되었습니다.' })).not.toBeInTheDocument();
  });

  it('비밀번호를 바꾸면 이미 로그인된 세션도 끊긴다', async () => {
    await signInAsDemo();
    renderApp('/reset-password');
    const u = user();
    await verifyIdentity(u, DEMO.member.name, '010-0000-0000', DEMO.loginId);
    await resetTo(u, NEW_PASSWORD);
    await screen.findByRole('heading', { level: 2, name: '비밀번호가 변경되었습니다.' });

    const header = document.querySelector<HTMLElement>('header.header')!;
    expect(await within(header).findByRole('link', { name: '로그인' })).toBeInTheDocument();
  });
});

describe('회원정보수정', () => {
  it('로그인하지 않았으면 로그인으로 보낸다', async () => {
    const { router } = renderApp('/me/profile');
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
  });

  it('아이디·이름·마스킹된 휴대전화·거주지 확인 상태를 읽기 전용으로 보이고 이메일과 거주지역을 고치게 한다', async () => {
    await signInAsDemo();
    renderApp('/me/profile');

    expect(await screen.findByRole('heading', { level: 1, name: '회원정보수정' })).toBeInTheDocument();
    expect(definition('아이디')).toHaveTextContent(DEMO.loginId);
    expect(definition('이름')).toHaveTextContent('예시회원');
    expect(definition('휴대전화')).toHaveTextContent('010-****-0000');
    expect(definition('거주지 확인')).toHaveTextContent('센터 확인 전');
    expect(screen.getByLabelText('이메일')).toHaveValue('demo@example.invalid');
    const region = screen.getByLabelText('거주지역 (본인 입력)');
    expect(within(region).getAllByRole('option').map((o) => o.textContent)).toEqual(['선택하지 않음', '조리읍', '그 외 파주시']);
    expect(screen.getByText(/우선접수는 센터가 확인한 거주지로 판정합니다/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '비밀번호 변경' })).toHaveAttribute('href', '/me/password');
    expect(screen.getByRole('link', { name: '회원탈퇴' })).toHaveAttribute('href', '/me/withdraw');
  });

  it('이메일과 거주지역을 저장하면 저장됨을 알리고 다시 열어도 유지된다', async () => {
    await signInAsDemo();
    const view = renderApp('/me/profile');
    const u = user();
    const email = await screen.findByLabelText('이메일');
    await u.clear(email);
    await u.type(email, 'new@example.test');
    await u.selectOptions(screen.getByLabelText('거주지역 (본인 입력)'), '조리읍');
    await u.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장되었습니다.')).not.toHaveClass('is-error');
    view.unmount();

    renderApp('/me/profile');
    expect(await screen.findByLabelText('이메일')).toHaveValue('new@example.test');
    expect(screen.getByLabelText('거주지역 (본인 입력)')).toHaveValue('JORI');
  });

  it('이메일 형식이 틀리면 서버에 묻지 않고 안내한다', async () => {
    await signInAsDemo();
    renderApp('/me/profile');
    const u = user();
    const email = await screen.findByLabelText('이메일');
    await u.clear(email);
    await u.type(email, 'not-an-email');
    await u.click(screen.getByRole('button', { name: '저장' }));
    expect(email).toHaveAccessibleDescription('이메일 주소 형식을 확인해 주세요.');
  });
});

describe('비밀번호 변경', () => {
  async function change(u: User, current: string, next: string, confirm = next) {
    await u.type(await screen.findByLabelText('현재 비밀번호'), current);
    await u.type(screen.getByLabelText('새 비밀번호'), next);
    await u.type(screen.getByLabelText('새 비밀번호 확인'), confirm);
    await u.click(screen.getByRole('button', { name: '변경' }));
  }

  it('현재 비밀번호가 맞으면 변경을 알리고 로그인 상태를 유지하며 새 비밀번호가 쓰인다', async () => {
    await signInAsDemo();
    const view = renderApp('/me/password');
    expect(await screen.findByRole('heading', { level: 1, name: '비밀번호 변경' })).toBeInTheDocument();
    const u = user();
    await change(u, DEMO.password, 'Changed-pass-123');

    expect(await screen.findByText('비밀번호가 변경되었습니다.')).not.toHaveClass('is-error');
    const header = document.querySelector<HTMLElement>('header.header')!;
    expect(within(header).getByText('예시회원님')).toBeInTheDocument();
    // 변경 직후에도 요청을 보낼 수 있어야 한다(서버가 바꾼 토큰을 다시 받는다).
    await view.router.navigate('/me/profile');
    await u.click(await screen.findByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장되었습니다.')).toBeInTheDocument();
  });

  it('현재 비밀번호가 틀리면 그 칸에 알린다', async () => {
    await signInAsDemo();
    renderApp('/me/password');
    await change(user(), 'wrong-password-1', 'Changed-pass-123');
    expect(await screen.findByLabelText('현재 비밀번호')).toHaveAccessibleDescription('현재 비밀번호가 올바르지 않습니다.');
  });

  it('새 비밀번호가 짧거나 확인과 다르면 서버에 묻지 않고 안내한다', async () => {
    await signInAsDemo();
    renderApp('/me/password');
    await change(user(), DEMO.password, 'short', 'different');
    expect(screen.getByLabelText('새 비밀번호')).toHaveAccessibleDescription(expect.stringContaining('10자 이상'));
    expect(screen.getByLabelText('새 비밀번호 확인')).toHaveAccessibleDescription('비밀번호가 서로 다릅니다.');
  });
});

describe('회원탈퇴', () => {
  async function submitWithdraw(u: User, password: string) {
    await u.type(await screen.findByLabelText('비밀번호 확인'), password);
    await u.click(screen.getByRole('button', { name: '회원탈퇴' }));
    await u.click(within(await screen.findByRole('group', { name: '회원탈퇴 확인' })).getByRole('button', { name: '탈퇴하기' }));
  }

  it('안내문, 선택 사유, 비밀번호 확인을 보이고 확인 단계에서 돌아가기를 누르면 탈퇴하지 않는다', async () => {
    await signInAsDemo();
    renderApp('/me/withdraw');
    expect(await screen.findByRole('heading', { level: 1, name: '회원탈퇴' })).toBeInTheDocument();
    expect(screen.getByText('진행 중인 수강신청·결제·환불 내역을 먼저 확인해 주세요.')).toBeInTheDocument();
    const reason = screen.getByLabelText('탈퇴 사유 (선택)');
    expect(within(reason).getAllByRole('option').map((o) => o.textContent)).toEqual([
      '선택하지 않음',
      '이용할 강좌가 없음',
      '이용이 어려움',
      '기타',
    ]);
    const u = user();
    await u.type(screen.getByLabelText('비밀번호 확인'), DEMO.password);
    await u.click(screen.getByRole('button', { name: '회원탈퇴' }));
    const confirm = screen.getByRole('group', { name: '회원탈퇴 확인' });
    expect(within(confirm).getByText(/탈퇴하면 30일 뒤 개인정보가 파기되며/)).toBeInTheDocument();
    await u.click(within(confirm).getByRole('button', { name: '돌아가기' }));

    expect(screen.queryByRole('group', { name: '회원탈퇴 확인' })).not.toBeInTheDocument();
    expect(within(document.querySelector<HTMLElement>('header.header')!).getByText('예시회원님')).toBeInTheDocument();
  });

  it('탈퇴하면 완료를 알리고 로그아웃되며 같은 계정으로 로그인할 수 없다', async () => {
    await signInAsDemo();
    const view = renderApp('/me/withdraw');
    const u = user();
    await u.selectOptions(await screen.findByLabelText('탈퇴 사유 (선택)'), '이용이 어려움');
    await submitWithdraw(u, DEMO.password);

    expect(await screen.findByText('회원탈퇴 처리가 완료되었습니다.')).toBeInTheDocument();
    const header = document.querySelector<HTMLElement>('header.header')!;
    expect(await within(header).findByRole('link', { name: '로그인' })).toBeInTheDocument();

    await view.router.navigate('/login');
    const form = await screen.findByRole('form', { name: '로그인' });
    await u.type(within(form).getByLabelText('아이디'), DEMO.loginId);
    await u.type(within(form).getByLabelText('비밀번호'), DEMO.password);
    await u.click(within(form).getByRole('button', { name: '로그인' }));
    expect(await screen.findByText('아이디 또는 비밀번호를 확인해 주세요.')).toBeInTheDocument();
  });

  it('진행 중인 신청이 있으면 서버 사유를 알리고 탈퇴하지 않는다', async () => {
    await signInAsDemo();
    await createApplication('1', crypto.randomUUID()); // 결제 대기 신청
    renderApp('/me/withdraw');
    await submitWithdraw(user(), DEMO.password);

    expect(await screen.findByText(/진행 중인 수강신청·결제·환불이 있어 탈퇴할 수 없습니다/)).toHaveClass('is-error');
    expect(within(document.querySelector<HTMLElement>('header.header')!).getByText('예시회원님')).toBeInTheDocument();
  });

  it('비밀번호가 틀리면 그 칸에 알린다', async () => {
    await signInAsDemo();
    renderApp('/me/withdraw');
    await submitWithdraw(user(), 'wrong-password-1');
    expect(await screen.findByLabelText('비밀번호 확인')).toHaveAccessibleDescription('비밀번호가 올바르지 않습니다.');
  });

  it('비밀번호를 비워 두면 서버에 묻지 않고 안내한다', async () => {
    await signInAsDemo();
    renderApp('/me/withdraw');
    await user().click(await screen.findByRole('button', { name: '회원탈퇴' }));
    expect(screen.getByLabelText('비밀번호 확인')).toHaveAccessibleDescription('비밀번호를 입력해 주세요.');
    expect(screen.queryByRole('group', { name: '회원탈퇴 확인' })).not.toBeInTheDocument();
  });
});

