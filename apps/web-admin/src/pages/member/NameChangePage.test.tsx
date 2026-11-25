// 이름 변경 검토(검토 중·처리한 목록, 두 번 확인 승인·반려, 처리 메모, 권한)를 확인하는 시험
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';
import { apiError } from '../../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async () => (await within(await screen.findByRole('region', { name: '이름 변경 요청 목록' })).findAllByRole('row')).slice(1);

describe('이름 변경 검토', () => {
  it('검토 중인 요청을 오래 걸린 것부터 새 이름·사유와 함께 보이고 현재 이름은 가려 보인다', async () => {
    await signInAs('group');
    renderApp('/mbr/name-changes');
    expect(await heading('이름 변경 검토')).toBeInTheDocument();
    const [first, second] = await rows();
    expect(cells(first!).slice(1, 6)).toEqual(['kim01', '김*원', '김새롬', '개명 판결문 확인 예정', '검토 중']);
    expect(cells(second!).slice(1, 6)).toEqual(['park02', '박*라', '박다온', '호적 정정으로 이름이 바뀌었습니다.', '검토 중']);
  });

  it('메뉴에 보이고 승인 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('group');
    const first = renderApp('/mbr/name-changes');
    expect(await within(await screen.findByRole('navigation', { name: '회원·콘텐츠 하위 메뉴' })).findByRole('link', { name: '이름 변경 검토' })).toBeInTheDocument();
    first.unmount();
    await signInAs('course');
    renderApp('/mbr/name-changes');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });

  it('두 번 확인해 승인하면 목록에서 빠지고 처리한 요청에 메모와 함께 남는다', async () => {
    await signInAs('group');
    renderApp('/mbr/name-changes');
    await rows();
    await userEvent.type(screen.getByLabelText('처리 메모(선택) (kim01 → 김새롬)'), '판결문 확인');
    await userEvent.click(screen.getByRole('button', { name: '승인 (kim01 → 김새롬)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 승인 (kim01 → 김새롬)' }));
    expect(await screen.findByRole('cell', { name: 'park02' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'kim01' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: '처리한 요청' }));
    const done = await rows();
    expect(cells(done[0]!).slice(1, 6)).toEqual(['kim01', '김*롬', '김새롬', '개명 판결문 확인 예정', '승인']);
    expect(cells(done[0]!)[6]).toContain('판결문 확인');
    expect(cells(done[0]!)[6]).toContain('김관리');
  });

  it('한 회원의 요청에 적은 메모는 다른 회원의 결정에 함께 보내지 않는다', async () => {
    const sent: unknown[] = [];
    await signInAs('group');
    renderApp('/mbr/name-changes');
    await rows();
    server.use(
      http.post('/api/admin/v1/name-change-requests/:id/reject', async ({ request }) => {
        sent.push(await request.json());
        return apiError('CONFLICT_STATE');
      }),
    );
    await userEvent.type(screen.getByLabelText('처리 메모(선택) (kim01 → 김새롬)'), '김씨에게만 보낼 사유');
    await userEvent.click(screen.getByRole('button', { name: '반려 (park02 → 박다온)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 반려 (park02 → 박다온)' }));
    await screen.findByRole('alert');
    expect(JSON.stringify(sent)).not.toContain('김씨에게만 보낼 사유');
    expect(sent).toHaveLength(1);
  });

  it('반려하면 처리한 요청에 반려로 남는다', async () => {
    await signInAs('group');
    renderApp('/mbr/name-changes');
    await rows();
    await userEvent.click(screen.getByRole('button', { name: '반려 (park02 → 박다온)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 반려 (park02 → 박다온)' }));
    expect(await screen.findByRole('cell', { name: 'kim01' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'park02' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: '처리한 요청' }));
    const done = await rows();
    expect(done.map((row) => cells(row)[1])).toEqual(['park02', 'lee03']);
    expect(cells(done[0]!)[5]).toBe('반려');
  });

  it('처리한 요청 목록에는 결정 단추와 메모 입력이 없다', async () => {
    await signInAs('group');
    renderApp('/mbr/name-changes?state=DECIDED');
    const [only] = await rows();
    expect(cells(only!).slice(1, 6)).toEqual(['lee03', '이*름', '이하늘', '개명 판결문 확인 예정', '승인']);
    expect(screen.queryByRole('button', { name: /승인 \(/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/처리 메모/)).not.toBeInTheDocument();
  });

  it('다른 담당자가 먼저 처리했으면 알리고 목록을 다시 읽는다', async () => {
    await signInAs('group');
    renderApp('/mbr/name-changes');
    await rows();
    server.use(http.post('/api/admin/v1/name-change-requests/:id/approve', () => apiError('CONFLICT_STATE')));
    await userEvent.click(screen.getByRole('button', { name: '승인 (kim01 → 김새롬)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 승인 (kim01 → 김새롬)' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('이미 다른 담당자가 처리했거나');
  });

  it('검토 중인 요청이 없으면 알린다', async () => {
    await signInAs('group');
    server.use(http.get('/api/admin/v1/name-change-requests', () => Response.json({ items: [] })));
    renderApp('/mbr/name-changes');
    expect(await screen.findByText('검토 중인 요청이 없습니다.')).toBeInTheDocument();
  });
});
