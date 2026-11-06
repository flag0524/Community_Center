// 권한 배정(목록 조건, 위임 가능한 역할만, 역할·범위·기간 한 행, 자기 배정 금지, 중복 거절, 회수)을 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { apiError } from '../../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);
const field = (name: string) => screen.getByLabelText(new RegExp(`^${name}`));
const ASSIGN = (n: number) => `70${String(n).padStart(20, '0')}`;
const optionNames = (select: HTMLElement) => within(select).getAllByRole('option').map((option) => option.textContent);
const fact = (name: string) => screen.getByText(name, { selector: 'dt' }).nextElementSibling?.textContent;

describe('권한 배정 목록', () => {
  it('유효한 배정이 먼저, 시작 전과 기간 종료가 뒤에 나온다', async () => {
    await signInAs('group');
    renderApp('/sys/roles');
    expect((await rows('배정 목록')).map((row) => cells(row))).toEqual([
      ['박정산', '결제·환불 담당자', '조리읍 묶음 전체', '2026-03-01 ~ 제한 없음', '유효'],
      ['이강좌', '강좌 담당자', '조리읍 묶음 전체', '2026-03-01 ~ 2030-12-31', '유효'],
      ['김관리', '운영묶음 관리자', '조리읍 묶음 전체', '2026-01-01 ~ 제한 없음', '유효'],
      ['박정산', '동 담당자', '조리읍', '2027-01-01 ~ 2027-12-31', '시작 전'],
      ['이강좌', '콘텐츠 담당자', '조리읍', '2025-01-01 ~ 2025-12-31', '기간 종료'],
    ]);
  });

  it('상태와 관리자 이름으로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/sys/roles');
    await rows('배정 목록');
    await userEvent.selectOptions(screen.getByLabelText('상태'), '시작 전');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('배정 목록')).map((row) => cells(row)[1])).toEqual(['동 담당자']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.type(await screen.findByLabelText('관리자 이름'), '이강좌');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('배정 목록')).length).toBe(2));
  });

  it('권한 배정 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('course');
    renderApp('/sys/roles');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('권한 배정 추가', () => {
  async function openForm() {
    await signInAs('group');
    renderApp('/sys/roles/new');
    await heading('권한 배정 추가');
    await screen.findByLabelText(/^관리자/);
  }

  it('나를 뺀 관리자와 내가 위임할 수 있는 역할만 고르게 한다', async () => {
    await openForm();
    expect(optionNames(field('관리자'))).toEqual(['선택', '이강좌', '박정산', '최담당']);
    expect(optionNames(field('역할'))).toEqual(['선택', '운영묶음 관리자', '동 담당자', '강좌 담당자', '콘텐츠 담당자', '결제·환불 담당자']);
  });

  it('역할에 따라 쓸 수 있는 범위가 정해지고 동 범위는 동을 고르게 한다', async () => {
    await openForm();
    await userEvent.selectOptions(field('역할'), '강좌 담당자');
    expect(screen.getByLabelText('운영묶음 전체')).not.toBeChecked();
    expect(screen.getByLabelText('동')).not.toBeChecked();
    expect(screen.queryByRole('combobox', { name: /^동/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('동'));
    expect(optionNames(screen.getByRole('combobox', { name: /^동/ }))).toEqual(['선택', '조리읍']);

    await userEvent.selectOptions(field('역할'), '운영묶음 관리자');
    expect(screen.getByLabelText('운영묶음 전체')).toBeChecked();
    expect(screen.queryByRole('combobox', { name: /^동/ })).not.toBeInTheDocument();
    expect(screen.getByText('AU.GRANT_W')).toBeInTheDocument();
  });

  it('필수 항목이 비면 저장하지 않는다', async () => {
    await openForm();
    await userEvent.click(screen.getByRole('button', { name: '배정' }));
    expect(screen.getAllByText('필수 항목입니다.')).toHaveLength(3);
  });

  it('배정하면 상세로 가고 목록에 쌓이며 한 행에 역할·범위·기간이 함께 남는다', async () => {
    await openForm();
    await userEvent.selectOptions(field('관리자'), '최담당');
    await userEvent.selectOptions(field('역할'), '결제·환불 담당자');
    await userEvent.click(screen.getByLabelText('운영묶음 전체'));
    await userEvent.type(field('유효 시작일'), '2026-11-10');
    await userEvent.click(screen.getByRole('button', { name: '배정' }));
    await heading('권한 배정 상세');
    expect(await screen.findByText('최담당')).toBeInTheDocument();
    expect(fact('범위')).toBe('조리읍 묶음 전체');
    expect(fact('유효기간')).toBe('2026-11-10 ~ 제한 없음');
    expect(fact('부여')).toMatch(/^김관리 · /);

    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    expect(await rows('배정 목록')).toHaveLength(6);
  });

  it('같은 관리자에게 같은 역할·범위의 유효한 배정이 있으면 거절하고 종료일은 시작일 뒤여야 한다', async () => {
    await openForm();
    await userEvent.selectOptions(field('관리자'), '박정산');
    await userEvent.selectOptions(field('역할'), '결제·환불 담당자');
    await userEvent.click(screen.getByLabelText('운영묶음 전체'));
    await userEvent.type(field('유효 시작일'), '2026-11-10');
    await userEvent.type(field('유효 종료일'), '2026-11-10');
    await userEvent.click(screen.getByRole('button', { name: '배정' }));
    expect(await screen.findByText('유효 종료일은 시작일 이후여야 합니다.')).toBeInTheDocument();
    expect(screen.getByText('같은 관리자에게 같은 역할·범위의 유효한 배정이 이미 있습니다.')).toBeInTheDocument();
  });

  it('동 범위에서 동을 고르지 않으면 요청을 보내지 않는다', async () => {
    let calls = 0;
    server.use(
      http.post('/api/admin/v1/role-assignments', () => {
        calls += 1;
        return apiError('RULE_REJECTED');
      }),
    );
    await openForm();
    await userEvent.selectOptions(field('관리자'), '최담당');
    await userEvent.selectOptions(field('역할'), '동 담당자');
    await userEvent.type(field('유효 시작일'), '2026-11-10');
    await userEvent.click(screen.getByRole('button', { name: '배정' }));
    expect(await screen.findByText('동을 선택해 주세요.')).toBeInTheDocument();
    expect(calls).toBe(0);
  });

  it('자기 자신에게는 줄 수 없다는 서버 답을 보인다', async () => {
    server.use(http.get('/api/admin/v1/role-assignment-options', () => HttpResponse.json({ admins: [{ id: '2000000000000000000001', name: '김관리' }], roles: [{ id: '7100000000000000000005', name: '콘텐츠 담당자', scopes: ['GROUP'], authorities: ['AU.POST_W', 'AU.SITE_W'] }], dongs: [] })));
    await openForm();
    await userEvent.selectOptions(field('관리자'), '김관리');
    await userEvent.selectOptions(field('역할'), '콘텐츠 담당자');
    await userEvent.type(field('유효 시작일'), '2026-11-10');
    await userEvent.click(screen.getByRole('button', { name: '배정' }));
    expect(await screen.findByText('자기 자신에게는 배정할 수 없습니다. 다른 권한 관리자에게 요청해 주세요.')).toBeInTheDocument();
  });
});

describe('권한 배정 상세와 회수', () => {
  it('유효한 배정은 주는 권한을 보이고 두 번 확인해 회수한다', async () => {
    await signInAs('group');
    renderApp(`/sys/roles/${ASSIGN(3)}`);
    await heading('권한 배정 상세');
    expect(fact('역할')).toBe('결제·환불 담당자');
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual(expect.arrayContaining(['AU.STLM_R', 'AU.STLM_W', 'AU.RFND_A', 'AU.RFND_X']));
    await userEvent.click(screen.getByRole('button', { name: '회수 (박정산 결제·환불 담당자)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 회수 (박정산 결제·환불 담당자)' }));
    expect(await screen.findByText('회수했습니다. 이 배정의 권한은 더 이상 쓸 수 없습니다.')).toBeInTheDocument();
    expect(fact('상태')).toBe('회수됨');
    expect(screen.queryByRole('button', { name: /^회수/ })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    await rows('배정 목록');
    await userEvent.selectOptions(screen.getByLabelText('상태'), '회수됨');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('배정 목록')).map((row) => cells(row)[0])).toEqual(['박정산']));
  });

  it.each([
    ['내 배정', 1],
    ['기간이 끝난 배정', 4],
  ])('%s은 회수 버튼이 없다', async (_name, n) => {
    await signInAs('group');
    renderApp(`/sys/roles/${ASSIGN(n)}`);
    await heading('권한 배정 상세');
    expect(screen.queryByRole('button', { name: /^회수/ })).not.toBeInTheDocument();
  });

  it('회수 요청에 읽은 버전을 싣고 규칙으로 거절되면 사유를 보인다', async () => {
    let sent: { version?: number } = {};
    server.use(
      http.get('/api/admin/v1/role-assignments/:id', () =>
        HttpResponse.json({ assignmentId: ASSIGN(3), adminName: '박정산', roleName: '결제·환불 담당자', scope: 'GROUP', scopeLabel: '조리읍 묶음 전체', validFrom: '2026-03-01', validTo: null, status: 'ACTIVE', grantedBy: '김관리', authorities: ['AU.STLM_R'], grantedAt: '2026-03-01T09:00:00+09:00', version: 4, canRevoke: true }),
      ),
      http.post('/api/admin/v1/role-assignments/:id/revoke', async ({ request }) => {
        sent = (await request.json()) as typeof sent;
        return apiError('RULE_REJECTED', { assignmentId: '자기 자신의 배정은 직접 회수할 수 없습니다.' });
      }),
    );
    await signInAs('group');
    renderApp(`/sys/roles/${ASSIGN(3)}`);
    await heading('권한 배정 상세');
    await userEvent.click(screen.getByRole('button', { name: '회수 (박정산 결제·환불 담당자)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 회수 (박정산 결제·환불 담당자)' }));
    expect(await screen.findByText('자기 자신의 배정은 직접 회수할 수 없습니다.')).toBeInTheDocument();
    expect(sent.version).toBe(4);
  });

  it('다른 곳에서 먼저 바뀌어 회수가 충돌하면 다시 열도록 안내한다', async () => {
    await signInAs('group');
    renderApp(`/sys/roles/${ASSIGN(3)}`);
    await heading('권한 배정 상세');
    server.use(http.post('/api/admin/v1/role-assignments/:id/revoke', () => apiError('VERSION_CONFLICT')));
    await userEvent.click(screen.getByRole('button', { name: '회수 (박정산 결제·환불 담당자)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 회수 (박정산 결제·환불 담당자)' }));
    expect(await screen.findByText('다른 곳에서 먼저 바뀌었습니다. 목록에서 다시 열어 주세요.')).toBeInTheDocument();
  });
});