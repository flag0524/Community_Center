// 이름 변경 요청(입력 검증, 비밀번호 재확인, 요청 후 검토 중 표시, 진행 중 요청이 있을 때, 승인·반려 결과, 링크)을 확인하는 시험
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DEMO, decideMockNameChange } from '../../mocks/auth';
import { renderApp, signInAsDemo, useMockServer } from '../../test/render';

useMockServer();

const user = () => userEvent.setup({ delay: null });
const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const fill = async (u: ReturnType<typeof user>, name: string, reason: string, password: string) => {
  await u.type(screen.getByLabelText('바꾸려는 이름'), name);
  await u.type(screen.getByLabelText('변경 사유'), reason);
  await u.type(screen.getByLabelText('비밀번호 확인'), password);
};
const REQ = (n: number) => `95${String(n).padStart(20, '0')}`;

describe('이름 변경 요청', () => {
  it('회원정보수정 화면에서 이름 변경 요청으로 이동하고 현재 이름과 안내를 보인다', async () => {
    await signInAsDemo();
    renderApp('/me/profile');
    await user().click(await screen.findByRole('link', { name: '이름 변경 요청' }));
    expect(await heading('이름 변경 요청')).toBeInTheDocument();
    expect(screen.getByText('현재 이름', { selector: 'dt' }).nextElementSibling).toHaveTextContent(DEMO.member.name);
    expect(screen.getByText('신분증 등 증빙은 센터를 방문해 확인합니다. 증빙을 확인한 뒤 승인하면 이름이 바뀝니다.')).toBeInTheDocument();
    expect(screen.getByText('요청한 내역이 없습니다.')).toBeInTheDocument();
  });

  it('비어 있거나 현재 이름과 같으면 서버에 묻지 않고 칸마다 안내한다', async () => {
    await signInAsDemo();
    renderApp('/me/name-change');
    await heading('이름 변경 요청');
    const u = user();
    await u.click(screen.getByRole('button', { name: '요청' }));
    expect(screen.getByLabelText('바꾸려는 이름')).toHaveAccessibleDescription('바꾸려는 이름을 입력해 주세요.');
    expect(screen.getByText('변경 사유를 입력해 주세요.')).toBeInTheDocument();
    expect(screen.getByLabelText('비밀번호 확인')).toHaveAccessibleDescription(/비밀번호를 입력해 주세요\./);
    await u.type(screen.getByLabelText('바꾸려는 이름'), DEMO.member.name);
    await u.click(screen.getByRole('button', { name: '요청' }));
    expect(screen.getByLabelText('바꾸려는 이름')).toHaveAccessibleDescription('현재 이름과 같습니다.');
  });

  it('비밀번호가 틀리면 서버 안내를 보이고 입력한 비밀번호를 비운다', async () => {
    await signInAsDemo();
    renderApp('/me/name-change');
    await heading('이름 변경 요청');
    const u = user();
    await fill(u, '김새롬', '개명했습니다', 'Wrong-pass-0000');
    await u.click(screen.getByRole('button', { name: '요청' }));
    expect(await screen.findByText('비밀번호가 올바르지 않습니다.')).toBeInTheDocument();
    expect(screen.getByLabelText('비밀번호 확인')).toHaveValue('');
    expect(screen.queryByText(/검토하고 있습니다/)).not.toBeInTheDocument(); // 요청되지 않았다
  });

  it('요청하면 검토 중으로 보이고 새 요청 양식 대신 안내를 보인다', async () => {
    await signInAsDemo();
    renderApp('/me/name-change');
    await heading('이름 변경 요청');
    const u = user();
    await fill(u, '김새롬', '개명했습니다', DEMO.password);
    await u.click(screen.getByRole('button', { name: '요청' }));
    expect(await screen.findByText('김새롬(으)로 바꾸는 요청을 센터에서 검토하고 있습니다. 처리가 끝나면 새 요청을 할 수 있습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: '이름 변경 요청' })).not.toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: '이름 변경 요청 내역' })).getByRole('listitem')).toHaveTextContent('김새롬 · 검토 중');
    expect(screen.getByText('현재 이름', { selector: 'dt' }).nextElementSibling).toHaveTextContent(DEMO.member.name); // 승인 전에는 바뀌지 않는다
  });

  it('승인되면 이름이 바뀌고 새 요청 양식이 다시 보이며 반려되면 센터 안내가 보인다', async () => {
    await signInAsDemo();
    const { unmount } = renderApp('/me/name-change');
    await heading('이름 변경 요청');
    const u = user();
    await fill(u, '김새롬', '개명했습니다', DEMO.password);
    await u.click(screen.getByRole('button', { name: '요청' }));
    await screen.findByText(/검토하고 있습니다/);
    unmount();

    decideMockNameChange(REQ(1), 'REJECTED', '증빙이 확인되지 않았습니다.');
    renderApp('/me/name-change');
    await heading('이름 변경 요청');
    const row = await within(await screen.findByRole('list', { name: '이름 변경 요청 내역' })).findByRole('listitem');
    expect(row).toHaveTextContent('반려');
    expect(row).toHaveTextContent('센터 안내: 증빙이 확인되지 않았습니다.');
    expect(screen.getByRole('form', { name: '이름 변경 요청' })).toBeInTheDocument(); // 결정이 끝나 다시 요청할 수 있다
  });

  it('승인한 요청은 승인으로 보이고 현재 이름이 새 이름이다', async () => {
    await signInAsDemo();
    const { unmount } = renderApp('/me/name-change');
    await heading('이름 변경 요청');
    const u = user();
    await fill(u, '김새롬', '개명했습니다', DEMO.password);
    await u.click(screen.getByRole('button', { name: '요청' }));
    await screen.findByText(/검토하고 있습니다/);
    unmount();

    decideMockNameChange(REQ(1), 'APPROVED');
    renderApp('/me/name-change');
    await heading('이름 변경 요청');
    expect(await within(await screen.findByRole('list', { name: '이름 변경 요청 내역' })).findByRole('listitem')).toHaveTextContent('승인(이름이 바뀌었습니다)');
    expect(screen.getByText('현재 이름', { selector: 'dt' }).nextElementSibling).toHaveTextContent('김새롬');
  });

  it('로그인하지 않으면 로그인 화면으로 보낸다', async () => {
    renderApp('/me/name-change');
    expect(await screen.findByRole('heading', { level: 1, name: '로그인' })).toBeInTheDocument();
  });
});
