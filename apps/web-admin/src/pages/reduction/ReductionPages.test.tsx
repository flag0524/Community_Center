// 감면 사전심사(접수 우선 목록, 증빙 내려받기 감사기록, 승인·반려 규칙, 재심사 새 건, 심사 권한 차이)와 처리 이력을 확인하는 시험
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';
import { apiError } from '../../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);
const field = (name: string) => screen.getByLabelText(new RegExp(`^${name}`));
const REVIEW = (n: number) => `80${String(n).padStart(20, '0')}`;
const FILE = (n: number) => `81${String(n).padStart(20, '0')}`;
const fact = (name: string) => screen.getByText(name, { selector: 'dt' }).nextElementSibling?.textContent;
const decide = () => userEvent.click(screen.getByRole('button', { name: '결정' }));

describe('감면 검토 목록', () => {
  it('접수된 심사가 오래된 신청부터 먼저, 결정된 심사가 뒤에 나온다', async () => {
    await signInAs('group');
    renderApp('/pay/reductions');
    expect((await rows('감면 심사 목록')).map((row) => cells(row))).toEqual([
      ['김○○', '2026년 제4기', '기초생활보장 수급자 본인', '2', '2026-10-20', '접수'],
      ['이○○', '2026년 제4기', '국가유공자 본인', '1', '2026-10-22', '접수'],
      ['박○○', '2026년 제4기', '등록 장애인 본인', '1', '2026-10-15', '승인'],
      ['최○○', '2026년 제4기', '기초생활보장 수급자 본인', '1', '2026-10-10', '반려'],
    ]);
  });

  it('기수 조건을 요청에 싣는다', async () => {
    const asked: Array<string | null> = [];
    server.use(
      http.get('/api/admin/v1/reductions', ({ request }) => {
        asked.push(new URL(request.url).searchParams.get('cycleId'));
        return Response.json({ items: [], page: 1, size: 20, total: 0, criteria: { basisAt: '2026-10-30T14:20:00+09:00', description: null } });
      }),
    );
    await signInAs('group');
    renderApp('/pay/reductions');
    await screen.findByText('조건에 맞는 심사가 없습니다.');
    await userEvent.selectOptions(await screen.findByLabelText('교육기수'), '2026년 제4기');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(() => expect(asked).toContain('1000000000000000000001'));
  });

  it('상태 조건으로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/pay/reductions');
    await rows('감면 심사 목록');
    await userEvent.selectOptions(screen.getByLabelText('상태'), '반려');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('감면 심사 목록')).map((row) => cells(row)[0])).toEqual(['최○○']));
  });
});

describe('감면 심사 상세', () => {
  it('증빙과 거주 확인을 보이고 검사를 통과한 파일만 내려받기 링크가 있다', async () => {
    await signInAs('group');
    renderApp(`/pay/reductions/${REVIEW(1)}`);
    await heading('감면 심사 상세');
    expect(fact('조리읍 거주 확인')).toBe('확인됨');
    expect((await rows('증빙 목록')).map((row) => cells(row))).toEqual([
      ['수급자 증명서.pdf', '정상', '내려받기'],
      ['가족관계증명서.pdf', '검사 대기', '-'],
    ]);
    expect(screen.getByRole('link', { name: '내려받기 (수급자 증명서.pdf)' })).toHaveAttribute('href', `/api/admin/v1/files/${FILE(1)}/download`);
    expect(screen.getByText('열람 기록이 없습니다.')).toBeInTheDocument();
  });

  it('증빙을 내려받으면 내려받은 사람과 시각이 열람 기록에 남는다', async () => {
    await signInAs('group');
    renderApp(`/pay/reductions/${REVIEW(1)}`);
    await heading('감면 심사 상세');
    const link = await screen.findByRole('link', { name: '내려받기 (수급자 증명서.pdf)' });
    link.addEventListener('click', (event) => event.preventDefault()); // jsdom은 페이지 이동을 구현하지 않아 경고를 낸다
    fireEvent.click(link); // 화면은 잠시 뒤 열람 기록을 다시 읽는다
    expect((await fetch(link.getAttribute('href')!)).status).toBe(200);
    await waitFor(async () => expect((await rows('열람 기록')).map((row) => cells(row).slice(1))).toEqual([['김관리', '수급자 증명서.pdf']]));
  });

  it('검사를 통과하지 않은 증빙은 내려받을 수 없다', async () => {
    await signInAs('group');
    expect((await fetch(`/api/admin/v1/files/${FILE(2)}/download`)).status).toBe(404);
    renderApp(`/pay/reductions/${REVIEW(1)}`);
    await heading('감면 심사 상세');
    expect(screen.queryByRole('link', { name: '내려받기 (가족관계증명서.pdf)' })).not.toBeInTheDocument();
  });

  it('심사 권한(신청 처리 쓰기)이 있는 다른 담당자도 증빙을 내려받을 수 있다', async () => {
    await signInAs('course');
    expect((await fetch(`/api/admin/v1/files/${FILE(1)}/download`)).status).toBe(200);
  });

  it('심사 권한이 없는 담당자는 증빙을 내려받을 수 없다', async () => {
    await signInAs('finance');
    expect((await fetch(`/api/admin/v1/files/${FILE(1)}/download`)).status).toBe(403);
  });
  it('승인은 유효 종료일이 필수이고 두 번 확인한 뒤 결정되며 더는 고칠 수 없다', async () => {
    await signInAs('group');
    renderApp(`/pay/reductions/${REVIEW(1)}`);
    await heading('감면 심사 상세');
    await decide();
    expect(screen.getByText('승인 유효 종료일을 입력해 주세요.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '정말 승인' })).not.toBeInTheDocument();

    await userEvent.type(field('승인 유효 종료일'), '2030-12-31');
    await decide();
    await userEvent.click(screen.getByRole('button', { name: '정말 승인' }));
    await waitFor(() => expect(fact('상태')).toBe('승인'));
    expect(fact('승인 유효 종료일')).toBe('2030-12-31');
    expect(fact('심사')).toMatch(/^김관리 · /);
    expect(screen.queryByRole('form', { name: '감면 심사' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '재심사 (김○○)' })).toBeInTheDocument();
  });

  it('반려는 사유가 필수이고 사유가 결과에 남는다', async () => {
    await signInAs('group');
    renderApp(`/pay/reductions/${REVIEW(1)}`);
    await heading('감면 심사 상세');
    await userEvent.click(screen.getByLabelText('반려'));
    await decide();
    expect(screen.getByText('반려 사유를 입력해 주세요.')).toBeInTheDocument();
    await userEvent.type(field('반려 사유'), '증빙이 부족합니다.');
    await decide();
    await userEvent.click(screen.getByRole('button', { name: '정말 반려' }));
    await waitFor(() => expect(fact('상태')).toBe('반려'));
    expect(fact('반려 사유')).toBe('증빙이 부족합니다.');
  });

  it('확인 단계에서 취소하면 결정하지 않는다', async () => {
    await signInAs('group');
    renderApp(`/pay/reductions/${REVIEW(1)}`);
    await heading('감면 심사 상세');
    await userEvent.type(field('승인 유효 종료일'), '2030-12-31');
    await decide();
    await userEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(screen.getByRole('button', { name: '결정' })).toBeInTheDocument();
    expect(fact('상태')).toBe('접수');
  });

  it('조리읍 거주가 확인되지 않은 회원은 승인할 수 없다는 서버 답을 보인다', async () => {
    await signInAs('group');
    renderApp(`/pay/reductions/${REVIEW(2)}`);
    await heading('감면 심사 상세');
    expect(fact('조리읍 거주 확인')).toBe('확인 안 됨');
    await userEvent.type(field('승인 유효 종료일'), '2030-12-31');
    await decide();
    await userEvent.click(screen.getByRole('button', { name: '정말 승인' }));
    expect(await screen.findByText('조리읍 거주 확인이 된 회원만 승인할 수 있습니다.')).toBeInTheDocument();
    expect(fact('상태')).toBe('접수');
  });

  it('지난 날짜의 유효 종료일은 서버가 거절한다', async () => {
    await signInAs('group');
    renderApp(`/pay/reductions/${REVIEW(1)}`);
    await heading('감면 심사 상세');
    await userEvent.type(field('승인 유효 종료일'), '2020-01-01');
    await decide();
    await userEvent.click(screen.getByRole('button', { name: '정말 승인' }));
    expect(await screen.findByText('유효 종료일은 오늘 이후여야 합니다.')).toBeInTheDocument();
  });

  it('결정한 심사를 다시 심사하면 이전 건은 그대로 두고 증빙이 없는 새 접수 건이 생긴다', async () => {
    await signInAs('group');
    renderApp(`/pay/reductions/${REVIEW(3)}`);
    await heading('감면 심사 상세');
    await userEvent.click(screen.getByRole('button', { name: '재심사 (박○○)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 재심사 (박○○)' }));
    await waitFor(() => expect(fact('상태')).toBe('접수'));
    expect(screen.getByText('제출된 증빙이 없습니다.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    const list = await rows('감면 심사 목록');
    expect(list).toHaveLength(5);
    expect(list.map((row) => cells(row)[5])).toEqual(['접수', '접수', '접수', '승인', '반려']);
  });

  it.each([
    ['접수 건은 증빙 내려받기와 심사 양식이', 1],
    ['결정된 건은 재심사 버튼이', 3],
  ])('심사 권한이 없는 담당자는 %s 없다', async (_name, n) => {
    await signInAs('finance');
    renderApp(`/pay/reductions/${REVIEW(n)}`);
    await heading('감면 심사 상세');
    expect(screen.queryByRole('form', { name: '감면 심사' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^재심사/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /^내려받기/ })).not.toBeInTheDocument();
  });

  it('결정 요청은 고른 결정에 해당하는 값만 싣고 읽은 버전을 함께 보낸다', async () => {
    const sent: Array<{ decision?: string; rejectReason?: string | null; validUntil?: string | null; version?: number }> = [];
    const detail = { reviewId: REVIEW(1), memberName: '김○○', cycleName: '2026년 제4기', reductionType: 'LIVELIHOOD', evidenceCount: 0, appliedOn: '2026-10-20', status: 'RECEIVED', residenceConfirmed: true, evidence: [], evidenceViews: [], reviewedBy: null, reviewedAt: null, reviewNote: null, rejectReason: null, validUntil: null, version: 5, canDecide: true, canReReview: false, canViewEvidence: true };
    server.use(
      http.get('/api/admin/v1/reductions/:id', () => Response.json(detail)),
      http.post('/api/admin/v1/reductions/:id/decision', async ({ request }) => {
        sent.push((await request.json()) as (typeof sent)[number]);
        return apiError('RULE_REJECTED', { decision: '시험용 거절' });
      }),
    );
    await signInAs('group');
    renderApp(`/pay/reductions/${REVIEW(1)}`);
    await heading('감면 심사 상세');
    await userEvent.click(screen.getByLabelText('반려'));
    await userEvent.type(field('반려 사유'), '사유');
    await userEvent.click(screen.getByLabelText('승인'));
    await userEvent.type(field('승인 유효 종료일'), '2030-12-31');
    await decide();
    await userEvent.click(screen.getByRole('button', { name: '정말 승인' }));
    await screen.findByText('시험용 거절');
    await userEvent.click(screen.getByLabelText('반려'));
    await userEvent.type(field('반려 사유'), '사유');
    await decide();
    await userEvent.click(screen.getByRole('button', { name: '정말 반려' }));
    await waitFor(() => expect(sent).toHaveLength(2));
    expect(sent[0]).toMatchObject({ decision: 'APPROVE', rejectReason: null, validUntil: '2030-12-31', version: 5 });
    expect(sent[1]).toMatchObject({ decision: 'REJECT', validUntil: null, version: 5 });
  });

  it('다른 곳에서 먼저 바뀌어 결정이 충돌하면 다시 열도록 안내한다', async () => {
    await signInAs('group');
    renderApp(`/pay/reductions/${REVIEW(1)}`);
    await heading('감면 심사 상세');
    server.use(http.post('/api/admin/v1/reductions/:id/decision', () => apiError('VERSION_CONFLICT')));
    await userEvent.type(field('승인 유효 종료일'), '2030-12-31');
    await decide();
    await userEvent.click(screen.getByRole('button', { name: '정말 승인' }));
    expect(await screen.findByText('다른 곳에서 먼저 바뀌었습니다. 목록에서 다시 열어 주세요.')).toBeInTheDocument();
  });
});

describe('감면 처리 이력', () => {
  it('판정마다 새 행으로 쌓인 이력을 최근 순으로 보인다', async () => {
    await signInAs('group');
    renderApp('/pay/reduction-history');
    expect((await rows('감면 처리 이력')).map((row) => cells(row))).toEqual([
      ['2026-10-25 10:00', '박○○', '2026년 제4기', '승인', '30,000원', '사전심사 승인 적용', '김관리', '1건', 'A20264-000101'],
      ['2026-10-21 14:30', '최○○', '2026년 제4기', '반려', '-', '증빙 부족', '김관리', '1건', '-'],
    ]);
  });

  it('결과와 기간으로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/pay/reduction-history');
    await rows('감면 처리 이력');
    await userEvent.selectOptions(screen.getByLabelText('결과'), '반려');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('감면 처리 이력')).map((row) => cells(row)[1])).toEqual(['최○○']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.type(await screen.findByLabelText('시작일'), '2026-10-24');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('감면 처리 이력')).map((row) => cells(row)[1])).toEqual(['박○○']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.type(await screen.findByLabelText('종료일'), '2026-10-22');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('감면 처리 이력')).map((row) => cells(row)[1])).toEqual(['최○○']));
  });
});