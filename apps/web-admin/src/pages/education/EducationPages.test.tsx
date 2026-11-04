// 교육기수·강좌 관리 화면의 목록 조건, 등록·수정, 서버 규칙 오류, 상태 전이 버튼, 권한 차이를 확인하는 시험
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';
import { apiError } from '../../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const field = (name: string) => screen.getByLabelText(new RegExp(`^${name}`));
const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const rowOf = async (name: string) => (await screen.findByRole('link', { name })).closest('tr') as HTMLElement;

async function openCourse(name: string) {
  renderApp('/edu/courses');
  await userEvent.click(await screen.findByRole('link', { name }));
  await heading('강좌 수정');
}

async function fillNewCourse(name: string) {
  await userEvent.selectOptions(await screen.findByLabelText(/^기수/), '2026년 제4기');
  await userEvent.selectOptions(field('분류'), '컴퓨터');
  await userEvent.selectOptions(field('대표강사'), '추순자');
  await userEvent.type(field('강좌명'), name);
  await userEvent.type(field('모집정원'), '20');
  await userEvent.type(field('대기정원'), '5');
  await userEvent.type(field('수강료'), '30000');
  fireEvent.change(field('접수 시작'), { target: { value: '2026-12-01T09:00' } });
  fireEvent.change(field('접수 종료'), { target: { value: '2026-12-05T18:00' } });
  fireEvent.change(field('교육 시작일'), { target: { value: '2026-12-10' } });
  fireEvent.change(field('교육 종료일'), { target: { value: '2026-12-30' } });
}

describe('교육기수', () => {
  it('목록에 기수와 연결 강좌 수가 보인다', async () => {
    await signInAs('group');
    renderApp('/edu/cycles');
    const row = await rowOf('2026년 제4기');
    expect(within(row).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      '2026',
      '4',
      '2026년 제4기',
      '2026-09-07 ~ 2026-09-11',
      '2026-10-01 ~ 2026-12-31',
      '8',
      '사용중',
      '수정',
    ]);
    expect(screen.getByText('총', { exact: false })).toHaveTextContent('총 2건');
  });

  it('비워 둔 항목은 요청 없이 항목별로 알려 준다', async () => {
    await signInAs('group');
    const requested: string[] = [];
    server.events.on('request:start', ({ request }) => requested.push(`${request.method} ${new URL(request.url).pathname}`));
    renderApp('/edu/cycles/new');
    await heading('교육기수 등록');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    server.events.removeAllListeners();
    expect(screen.getAllByText('필수 항목입니다.').length).toBe(7);
    expect(requested.filter((request) => request.startsWith('POST /api/admin/v1/cycles'))).toEqual([]);
  });

  it('등록하면 수정 화면으로 가고 목록에 새 기수가 보인다', async () => {
    await signInAs('group');
    renderApp('/edu/cycles/new');
    await heading('교육기수 등록');
    await userEvent.type(field('기수명'), '2027년 제2기');
    await userEvent.type(field('교육연도'), '2027');
    await userEvent.type(field('차수'), '2');
    fireEvent.change(field('모집 시작일'), { target: { value: '2027-03-01' } });
    fireEvent.change(field('모집 종료일'), { target: { value: '2027-03-10' } });
    fireEvent.change(field('교육 시작일'), { target: { value: '2027-04-01' } });
    fireEvent.change(field('교육 종료일'), { target: { value: '2027-06-30' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await heading('교육기수 수정');
    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    expect(await rowOf('2027년 제2기')).toBeInTheDocument();
  });

  it('종료일이 시작일보다 빠르면 서버 오류를 해당 항목 아래에 보인다', async () => {
    await signInAs('group');
    renderApp('/edu/cycles/1000000000000000000002');
    await heading('교육기수 수정');
    fireEvent.change(field('모집 종료일'), { target: { value: '2026-11-01' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('모집 종료일은 시작일 이후여야 합니다.')).toBeInTheDocument();
    expect(field('모집 종료일')).toHaveAttribute('aria-invalid', 'true');
  });

  it('수정을 저장하면 저장했다고 알리고 화면에 남는다', async () => {
    await signInAs('group');
    renderApp('/edu/cycles/1000000000000000000002');
    await heading('교육기수 수정');
    await userEvent.type(field('기수명'), ' 확정');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect(field('기수명')).toHaveValue('2027년 제1기 확정');
  });

  it('연결 강좌가 있으면 기간 변경 영향 안내를 보인다', async () => {
    await signInAs('group');
    renderApp('/edu/cycles/1000000000000000000001');
    expect(await screen.findByText(/연결된 강좌가 8건/)).toBeInTheDocument();
  });

  it('다른 곳에서 먼저 수정되었으면 최신 내용을 다시 열라고 안내한다', async () => {
    await signInAs('group');
    renderApp('/edu/cycles/1000000000000000000002');
    await heading('교육기수 수정');
    server.use(http.put('/api/admin/v1/cycles/:id', () => apiError('VERSION_CONFLICT')));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('다른 곳에서 먼저 수정되었습니다.');
  });

  it('교육기수 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('course');
    renderApp('/edu/cycles');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('강좌 목록', () => {
  it('강좌와 정원·점유·대기, 수강료, 상태를 보여 준다', async () => {
    await signInAs('group');
    renderApp('/edu/courses');
    const row = await rowOf('초급컴퓨터');
    expect(within(row).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      '초급컴퓨터',
      '2026년 제4기',
      '컴퓨터',
      '추순자',
      '2026-09-07 ~ 2026-09-11',
      '20 / 20 / 6',
      '60,000원',
      '공개접수종료',
      '상세',
    ]);
    expect(await screen.findByText('총', { exact: false })).toHaveTextContent('총 8건');
  });

  it('검색어를 제출하면 주소에 담기고 맞는 강좌만 남는다', async () => {
    await signInAs('group');
    const { router } = renderApp('/edu/courses');
    await userEvent.type(await screen.findByLabelText('검색어'), '요가');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(() => expect(router.state.location.search).toBe('?q=%EC%9A%94%EA%B0%80'));
    expect(await screen.findByRole('link', { name: '요가A(중급)' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '초급컴퓨터' })).not.toBeInTheDocument();
    expect(await screen.findByText('총', { exact: false })).toHaveTextContent('총 1건');
  });

  it('상태 조건은 그 상태의 강좌만 보이고 조건 지우기로 되돌린다', async () => {
    await signInAs('group');
    renderApp('/edu/courses');
    await userEvent.selectOptions(await screen.findByLabelText('상태'), '작성중');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    expect(await screen.findByRole('link', { name: '[시험용] 작성중 강좌' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '초급컴퓨터' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    expect(await screen.findByRole('link', { name: '초급컴퓨터' })).toBeInTheDocument();
  });

  it('조건에 맞는 강좌가 없으면 안내한다', async () => {
    await signInAs('group');
    renderApp('/edu/courses?q=없는강좌');
    expect(await screen.findByText('조건에 맞는 강좌가 없습니다.')).toBeInTheDocument();
  });

  it('조회 권한만 있는 담당자에게는 등록 버튼이 없다', async () => {
    await signInAs('group');
    server.use(
      http.get('/api/admin/v1/me/permissions', () =>
        Response.json({
          roleNames: ['조회 담당'],
          scopeLabel: '조리읍 운영묶음',
          authorities: ['AU.CORS_R'],
          menu: [{ key: 'edu', title: '교육 운영', items: [{ key: 'courses', label: '강좌 관리', path: '/edu/courses' }] }],
        }),
      ),
    );
    renderApp('/edu/courses');
    await screen.findByRole('link', { name: '초급컴퓨터' });
    expect(screen.queryByRole('link', { name: '등록' })).not.toBeInTheDocument();
  });

  it('강좌 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('finance');
    renderApp('/edu/courses');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('강좌 등록·수정', () => {
  it('작성중 강좌는 저장·공개 요청·목록 버튼만 있고 공개하면 폐강 처리가 나타난다', async () => {
    await signInAs('group');
    await openCourse('[시험용] 작성중 강좌');
    expect(screen.getByText('상태: 작성중 · 접수예정 · 교육예정')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '접수 마감' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '폐강 처리' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '공개 요청' }));
    expect(await screen.findByText(/^상태: 공개/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '공개 요청' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '폐강 처리' })).toBeInTheDocument();
  });

  it('새 강좌를 등록하면 작성중으로 열리고 일정이 없어 공개 요청이 거절된다', async () => {
    await signInAs('group');
    renderApp('/edu/courses/new');
    await heading('강좌 등록');
    await fillNewCourse('저녁 컴퓨터');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await heading('강좌 수정');
    expect(screen.getByText(/^상태: 작성중/)).toBeInTheDocument();
    expect(screen.getByText(/등록 0건/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '공개 요청' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('일정이 1건 이상 있어야 공개할 수 있습니다.');
  });

  it('비워 둔 필수 항목은 알려 준다. 운영 동은 기본값이 있고 관외 접수 시작은 비워도 된다', async () => {
    await signInAs('group');
    renderApp('/edu/courses/new');
    await heading('강좌 등록');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(screen.getAllByText('필수 항목입니다.').length).toBe(11);
  });

  it('기수 교육기간을 벗어나면 서버 오류를 해당 항목 아래에 보인다', async () => {
    await signInAs('group');
    renderApp('/edu/courses/new');
    await heading('강좌 등록');
    await fillNewCourse('기간 초과');
    fireEvent.change(field('교육 종료일'), { target: { value: '2027-02-01' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('기수 교육기간 안이어야 합니다.')).toBeInTheDocument();
  });

  it('모집정원을 현재 점유보다 작게 줄일 수 없다', async () => {
    await signInAs('group');
    await openCourse('[시험용] 접수중 강좌');
    expect(screen.getByText('점유 12명 · 대기 0명')).toBeInTheDocument();
    await userEvent.clear(field('모집정원'));
    await userEvent.type(field('모집정원'), '5');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('현재 점유 12명보다 작게 줄일 수 없습니다.')).toBeInTheDocument();
  });

  it('수정을 저장하면 저장했다고 알리고 목록에 반영된다', async () => {
    await signInAs('group');
    await openCourse('[시험용] 접수중 강좌');
    fireEvent.change(field('강좌명'), { target: { value: '[시험용] 접수중 강좌 수정' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    expect(await screen.findByRole('link', { name: '[시험용] 접수중 강좌 수정' })).toBeInTheDocument();
  });

  it('고치지 않고 저장해도 접수 시각이 한국시간 그대로 유지된다', async () => {
    await signInAs('group');
    await openCourse('[시험용] 접수중 강좌');
    const before = [(field('접수 시작') as HTMLInputElement).value, (field('접수 종료') as HTMLInputElement).value];
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await screen.findByText('저장했습니다.');
    // 서버에 저장된 값을 다시 읽어 확인한다. 화면이 들고 있던 입력값과 비교하면 변환 오류를 놓친다.
    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    await userEvent.click(await screen.findByRole('link', { name: '[시험용] 접수중 강좌' }));
    await heading('강좌 수정');
    expect([(field('접수 시작') as HTMLInputElement).value, (field('접수 종료') as HTMLInputElement).value]).toEqual(before);
    expect(before[0]).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
  });

  it('다른 곳에서 먼저 수정되었으면 안내한다', async () => {
    await signInAs('group');
    await openCourse('[시험용] 접수중 강좌');
    server.use(http.put('/api/admin/v1/courses/:id', () => apiError('VERSION_CONFLICT')));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('다른 곳에서 먼저 수정되었습니다.');
  });

  it('접수 마감 버튼은 접수중인 공개 강좌에서만 나타나고 누르면 접수마감이 된다', async () => {
    await signInAs('group');
    await openCourse('초급컴퓨터');
    expect(screen.queryByRole('button', { name: '접수 마감' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    await userEvent.click(await screen.findByRole('link', { name: '[시험용] 접수중 강좌' }));
    await heading('강좌 수정');
    await userEvent.click(screen.getByRole('button', { name: '접수 마감' }));
    expect(await screen.findByText(/^상태: 접수마감/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '접수 마감' })).not.toBeInTheDocument();
  });
});

describe('폐강 처리', () => {
  it('영향 건수와 환불 완료가 아니라는 안내를 보이고 사유를 적어야 처리된다', async () => {
    await signInAs('group');
    await openCourse('요가A(중급)');
    await userEvent.click(screen.getByRole('button', { name: '폐강 처리' }));
    const dialog = await screen.findByRole('dialog', { name: '폐강 처리' });
    expect(await within(dialog).findByText('신청 39건, 결제 28건이 영향을 받습니다.')).toBeInTheDocument();
    expect(within(dialog).getByText(/폐강은 환불 완료가 아닙니다/)).toBeInTheDocument();
    const confirm = within(dialog).getByRole('button', { name: '폐강 처리' });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/^폐강 사유/), '수강 인원 미달');
    await userEvent.click(confirm);
    await waitFor(() => expect(screen.getByText(/^상태: 폐강/)).toBeInTheDocument());
    // 폐강된 강좌는 고칠 수 없다.
    expect(screen.queryByRole('button', { name: '저장' })).not.toBeInTheDocument();
    expect(field('강좌명')).toBeDisabled();
  });

  it('닫기를 누르면 처리하지 않고 닫힌다', async () => {
    await signInAs('group');
    await openCourse('요가A(중급)');
    await userEvent.click(screen.getByRole('button', { name: '폐강 처리' }));
    const dialog = await screen.findByRole('dialog', { name: '폐강 처리' });
    await userEvent.click(within(dialog).getByRole('button', { name: '닫기' }));
    await waitFor(() => expect(dialog).not.toHaveAttribute('open'));
    expect(screen.getByText(/^상태: 공개/)).toBeInTheDocument();
  });
});