// 수강신청 관리와 대기·자리 배정 화면의 목록 조건, 상세 원장 이력, 조회 전용 규칙, 개인정보 가림, 권한 차이를 확인하는 시험
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);

const APP = (n: number) => `12${String(n).padStart(20, '0')}`;
const COURSE_1 = '4000000000000000000001';

describe('수강신청 목록', () => {
  it('접수시각이 늦은 순서로 신청번호·강좌·가려진 이름·상태를 보여 준다', async () => {
    await signInAs('group');
    renderApp('/pay/applications');
    const list = await rows('수강신청 목록');
    expect(list.length).toBe(11);
    expect(cells(list[0]!)).toEqual(['A20264-000211', '요가A(중급)', '오○○', '수강확정', '결제완료', '접수', '2026-09-09 09:30']);
    expect(await screen.findByText('총', { exact: false })).toHaveTextContent('총 11건');
  });

  it('신청 상태와 결제 상태를 합친 표시 상태를 서버가 정한 대로 보인다', async () => {
    await signInAs('group');
    renderApp('/pay/applications?courseId=' + COURSE_1);
    const list = await rows('수강신청 목록');
    expect(list.map((row) => cells(row)[3])).toEqual(['신청취소', '대기', '대기', '결제 결과 확인 중', '결제대기', '수강확정']);
  });

  it('검색어·신청 상태·결제 상태·접수일 조건으로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/pay/applications');
    await userEvent.type(await screen.findByLabelText('검색어'), 'A20264-000203');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('수강신청 목록')).map((row) => cells(row)[2])).toEqual(['박○○']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.selectOptions(await screen.findByLabelText('신청 상태'), '대기');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('수강신청 목록')).length).toBe(3));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.selectOptions(await screen.findByLabelText('결제 상태'), '승인 결과 확인 중');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('수강신청 목록')).map((row) => cells(row)[2])).toEqual(['박○○']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    fireEvent.change(await screen.findByLabelText('접수일 시작'), { target: { value: '2026-09-09' } });
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('수강신청 목록')).length).toBe(1));
  });

  it('조건에 맞는 신청이 없으면 안내한다', async () => {
    await signInAs('group');
    renderApp('/pay/applications?q=없는신청');
    expect(await screen.findByText('조건에 맞는 신청이 없습니다.')).toBeInTheDocument();
  });

  it('신청 조회 권한이 있는 결제 담당자와 강좌 담당자는 화면을 볼 수 있다', async () => {
    await signInAs('finance');
    const first = renderApp('/pay/applications');
    expect(await screen.findByRole('region', { name: '수강신청 목록' })).toBeInTheDocument();
    first.unmount();
    await signInAs('course');
    renderApp('/pay/applications');
    expect(await screen.findByRole('region', { name: '수강신청 목록' })).toBeInTheDocument();
  });
});

describe('수강신청 상세', () => {
  it('확정된 신청은 이력·연결 결제·멱등 재요청을 보인다', async () => {
    await signInAs('group');
    renderApp(`/pay/applications/${APP(1)}`);
    await heading('수강신청 상세');
    expect(screen.getByText('A20264-000201')).toBeInTheDocument();
    const history = (await rows('상태 변경 이력')).map(cells);
    expect(history).toEqual([
      ['2026-09-07 09:00', '-', '자리 점유(결제 대기)', '회원', '신청 접수, 자리 배정'],
      ['2026-09-07 09:03', '자리 점유(결제 대기)', '확정', 'SYSTEM', '결제 승인'],
    ]);
    expect(screen.queryByText('대기 순번')).not.toBeInTheDocument();
    expect(screen.getByText('ORD-20260907-000001')).toBeInTheDocument();
    expect(screen.getByText('60,000원')).toBeInTheDocument();
    expect(screen.getByText('연결된 환불이 없습니다.')).toBeInTheDocument();
    expect((await rows('멱등 재요청 기록')).map(cells)).toEqual([['2026-09-07 09:00', '이전 결과 반환']]);
  });

  it('같은 키에 다른 내용으로 온 재요청은 내용 불일치로 기록된다', async () => {
    await signInAs('group');
    renderApp(`/pay/applications/${APP(3)}`);
    await heading('수강신청 상세');
    expect((await rows('멱등 재요청 기록')).map((row) => cells(row)[1])).toEqual(['내용 불일치(409)']);
    expect(screen.getByText('승인 결과 확인 중')).toBeInTheDocument();
  });

  it('대기 신청은 대기 순번을 보이고 자리 배정·결제기한은 없다', async () => {
    await signInAs('group');
    renderApp(`/pay/applications/${APP(4)}`);
    await heading('수강신청 상세');
    expect(screen.getByText('1번')).toBeInTheDocument();
    expect(screen.getAllByText('-').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('연결된 결제가 없습니다.')).toBeInTheDocument();
    expect(screen.getByText('재요청 기록이 없습니다.')).toBeInTheDocument();
  });

  it('환불이 연결된 신청은 환불번호와 상태를 보이고 상태를 바꾸는 버튼은 없다', async () => {
    await signInAs('group');
    renderApp(`/pay/applications/${APP(6)}`);
    await heading('수강신청 상세');
    expect(screen.getByText('R20264-000006')).toBeInTheDocument();
    expect(screen.getByText('완료')).toBeInTheDocument();
    expect(screen.getByText('관리자는 신청 상태를 직접 바꿀 수 없습니다. 방문·유선 환불 접수는 환불 화면에서 합니다.')).toBeInTheDocument();
    // 공통 머리글의 버튼은 빼고 본문에 상태를 바꾸는 버튼이 없는지만 본다.
    expect(within(screen.getByRole('main')).queryByRole('button')).not.toBeInTheDocument();
  });

  it('없는 신청은 찾을 수 없다고 알린다', async () => {
    await signInAs('group');
    renderApp(`/pay/applications/${APP(99)}`);
    expect(await screen.findByRole('alert')).toHaveTextContent('요청한 정보를 찾을 수 없습니다.');
  });
});

describe('대기·자리 배정', () => {
  it('강좌별 정원·점유·대기 수·다음 순번·최근 승격 시각을 보인다', async () => {
    await signInAs('group');
    renderApp('/pay/waitlist');
    const list = await rows('강좌별 대기 현황');
    expect(cells(list[0]!)).toEqual(['초급컴퓨터', '20', '20', '6', '1번', '2026-09-09 10:15', '상세']);
    expect(cells(list[7]!)[3]).toBe('0');
    expect(cells(list[7]!)[4]).toBe('-');
    expect(screen.getByText('자리는 비는 즉시 대기 순서대로 자동 배정됩니다. 수동 승격은 없습니다.')).toBeInTheDocument();
  });

  it('상세에서 대기자 순번과 승격 이력(문자 결과 포함)을 보이고 수동 승격 버튼은 없다', async () => {
    await signInAs('group');
    renderApp(`/pay/waitlist/${COURSE_1}`);
    await heading('대기·자리 배정 상세');
    const waiters = (await rows('대기자 순번')).map(cells);
    expect(waiters.length).toBe(6);
    expect(waiters[0]).toEqual(['1', 'A20264-001001', '이○○', '2026-09-07 09:10']);
    const promotions = (await rows('승격 이력')).map(cells);
    expect(promotions).toEqual([
      ['2026-09-08 14:02', 'A20264-001001', '2026-09-08 14:12', '발송 완료'],
      ['2026-09-09 10:15', 'A20264-001002', '2026-09-09 10:25', '발송 실패'],
    ]);
    // 공통 머리글의 버튼은 빼고 본문에 상태를 바꾸는 버튼이 없는지만 본다.
    expect(within(screen.getByRole('main')).queryByRole('button')).not.toBeInTheDocument();
  });

  it('대기자도 승격 이력도 없는 강좌는 그렇게 안내한다', async () => {
    await signInAs('group');
    renderApp('/pay/waitlist/4000000000000000000008');
    await heading('대기·자리 배정 상세');
    expect(await screen.findByText('대기자가 없습니다.')).toBeInTheDocument();
    expect(screen.getByText('승격 이력이 없습니다.')).toBeInTheDocument();
  });
});