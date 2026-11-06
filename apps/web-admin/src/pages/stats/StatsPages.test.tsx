// 대시보드(접수 현황, 권한별 확인할 업무, 강좌별 수요)와 통계 5개 탭(조건, 자료 없음과 0의 구분, 확인 중 금액 분리)을 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);
const fact = (name: string) => screen.getByText(name, { selector: 'dt' }).nextElementSibling?.textContent;
const NO_SOURCE = { basis: { basisAt: '2026-10-30T14:20:00+09:00', cycleId: null, fromDate: null, toDate: null }, source: null, rows: [], respondents: null, items: [] };

describe('대시보드', () => {
  it('기수의 접수 현황과 순수납을 원자료 집계로 보인다', async () => {
    await signInAs('group');
    renderApp('/dashboard');
    await screen.findByRole('heading', { name: '접수 현황' });
    await waitFor(() => expect(fact('신청건')).toBe('62'));
    expect(fact('고유 신청자')).toBe('55');
    expect(fact('등록완료')).toBe('37');
    expect(fact('좌석점유')).toBe('43');
    expect(fact('대기')).toBe('8');
    expect(fact('취소')).toBe('11');
    expect(fact('순수납')).toBe('7,240,000원');
    expect(screen.getByLabelText('교육기수')).toHaveValue('1000000000000000000001');
  });

  it('기수를 고르지 않으면 목록의 첫 기수로 조회한다', async () => {
    const asked: Array<string | null> = [];
    server.use(
      http.get('/api/admin/v1/dashboard', ({ request }) => {
        asked.push(new URL(request.url).searchParams.get('cycleId'));
        return HttpResponse.json({ basis: { basisAt: '2026-10-30T14:20:00+09:00', cycleId: null, fromDate: null, toDate: null }, summary: null, tasks: [], demand: [], recent: [] });
      }),
    );
    await signInAs('group');
    renderApp('/dashboard');
    await screen.findByText('자료 없음. 이 기수에는 집계할 신청이 아직 없습니다.');
    expect(asked).toEqual(['1000000000000000000001']);
  });

  it('확인할 업무는 권한이 있는 종류만 건수와 함께 보이고 누르면 조건이 걸린 목록으로 간다', async () => {
    await signInAs('group');
    renderApp('/dashboard');
    const section = await screen.findByRole('region', { name: '확인할 업무' });
    const links = await within(section).findAllByRole('link');
    expect(links.map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
      ['승인 결과 확인 1건', '/pay/transactions?status=PENDING'],
      ['환불 검토 대기 2건', '/pay/refunds?status=REQUESTED'],
      ['강사 심사 대기 1건', '/edu/instructors?status=PENDING'],
      ['문의 답변 대기 3건', '/mbr/inquiries?status=RECEIVED'],
      ['문자 발송 실패 4건', '/sys/sms'],
    ]);
  });

  it('정산 담당자에게는 정산 관련 업무만 보인다', async () => {
    await signInAs('finance');
    renderApp('/dashboard');
    const section = await screen.findByRole('region', { name: '확인할 업무' });
    expect((await within(section).findAllByRole('link')).map((link) => link.textContent)).toEqual(['승인 결과 확인 1건', '환불 검토 대기 2건']);
  });

  it('강좌별 유효수요와 정원 비율, 최근 작업을 보인다', async () => {
    await signInAs('group');
    renderApp('/dashboard');
    expect((await rows('강좌별 수요 표')).map((row) => cells(row))).toEqual([
      ['건강요가 초급', '25/20', '125%'],
      ['스마트폰 기초', '18/20', '90%'],
      ['서예교실', '8/15', '53%'],
    ]);
    expect((await rows('최근 작업 표')).map((row) => cells(row).slice(1))).toEqual([
      ['SYSTEM', '대기 승격', '건강요가 초급'],
      ['박정산', '환불 승인', 'R20264-000012'],
    ]);
  });

  it('신청이 없는 기수는 0이 아니라 자료 없음으로 보인다', async () => {
    await signInAs('group');
    renderApp('/dashboard');
    await screen.findByRole('heading', { name: '접수 현황' });
    await userEvent.selectOptions(await screen.findByLabelText('교육기수'), '2027년 제1기');
    expect(await screen.findByText('자료 없음. 이 기수에는 집계할 신청이 아직 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText('신청건')).not.toBeInTheDocument();
  });
});

describe('통계 수요·정산·출석', () => {
  it('수요 통계는 상태별 건수와 유효수요/정원을 보인다', async () => {
    await signInAs('group');
    renderApp('/stats');
    await heading('수요·연령·정산 통계');
    expect((await rows('수요 통계')).map((row) => cells(row))).toEqual([
      ['건강요가 초급', '생활체육/건강', '20', '31', '28', '14', '3', '1', '7', '6', '18', '25', '125%'],
      ['스마트폰 기초', '컴퓨터', '20', '22', '21', '15', '2', '0', '1', '4', '17', '18', '90%'],
      ['서예교실', '문화/취미', '15', '9', '9', '8', '0', '0', '0', '1', '8', '8', '53%'],
    ]);
  });

  it('분야 조건으로 좁히고 자료가 없는 기수는 자료 없음으로 구분한다', async () => {
    await signInAs('group');
    renderApp('/stats');
    await rows('수요 통계');
    await userEvent.selectOptions(screen.getByLabelText('분야'), '생활체육/건강');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('수요 통계')).map((row) => cells(row)[0])).toEqual(['건강요가 초급']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.selectOptions(await screen.findByLabelText('교육기수'), '2027년 제1기');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    expect(await screen.findByText('자료 없음. 조건에 맞는 신청이 없습니다.')).toBeInTheDocument();
  });

  it('정산 통계는 확인 중 금액을 순수납에 넣지 않고 따로 보인다', async () => {
    await signInAs('group');
    renderApp('/stats?tab=settlement');
    await screen.findByRole('region', { name: '결제수단별 정산' });
    expect(fact('승인금액')).toBe('7,640,000원');
    expect(fact('완료환불액')).toBe('400,000원');
    expect(fact('순수납')).toBe('7,240,000원');
    expect(fact('확인 중 금액')).toBe('120,000원 (순수납에 넣지 않았습니다)');
    expect((await rows('결제수단별 정산')).map((row) => cells(row))).toEqual([
      ['카드', '5,000,000원', '300,000원', '4,700,000원'],
      ['계좌이체', '2,640,000원', '100,000원', '2,540,000원'],
    ]);
  });

  it('결제가 없는 기수의 정산은 0원이 아니라 자료 없음으로 보인다', async () => {
    await signInAs('group');
    renderApp('/stats?tab=settlement&cycleId=1000000000000000000002');
    expect(await screen.findByText('자료 없음. 조건에 맞는 결제가 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText('승인금액', { selector: 'dt' })).not.toBeInTheDocument();
  });

  it('출석 통계는 체크한 건이 없으면 0%가 아니라 체크 없음으로 보이고 내려받기 안내가 없다', async () => {
    await signInAs('group');
    renderApp('/stats?tab=attendance');
    expect((await rows('출석 통계')).map((row) => cells(row))).toEqual([
      ['건강요가 초급', '김강사', '90', '10', '90%'],
      ['스마트폰 기초', '이강사', '71', '29', '71%'],
      ['서예교실', '박강사', '0', '0', '체크 없음'],
    ]);
    expect(screen.getByText(/출석 통계는 내려받을 수 없습니다/)).toBeInTheDocument();
  });
});

describe('통계 만족도·연령 성별', () => {
  it('연령·성별은 승인된 자료의 버전과 기준일을 함께 보인다', async () => {
    await signInAs('group');
    renderApp('/stats?tab=age');
    expect((await rows('연령·성별 통계')).map((row) => cells(row))).toEqual([
      ['20~39세', '12명', '48명', '0명'],
      ['40~59세', '35명', '120명', '2명'],
      ['60세 이상', '80명', '210명', '0명'],
    ]);
    expect(fact('자료 버전')).toBe('2026-상반기 v2');
    expect(fact('기준일')).toBe('2026-06-30');
  });

  it('승인된 집계자료가 없으면 0명이 아니라 미제공으로 보인다', async () => {
    server.use(http.get('/api/admin/v1/stats/age-gender', () => HttpResponse.json(NO_SOURCE)), http.get('/api/admin/v1/stats/satisfaction', () => HttpResponse.json(NO_SOURCE)));
    await signInAs('group');
    renderApp('/stats?tab=age');
    expect(await screen.findByText('미제공. 기관이 제공해 승인한 집계자료가 아직 없습니다.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: '만족도' }));
    expect(await screen.findByText('미제공. 기관이 제공해 승인한 만족도 자료가 아직 없습니다.')).toBeInTheDocument();
  });

  it('만족도는 평균과 분포를 보이고 응답이 없는 문항은 평균을 산출하지 않는다', async () => {
    await signInAs('group');
    renderApp('/stats?tab=satisfaction');
    expect((await rows('만족도 통계')).map((row) => cells(row))).toEqual([
      ['강의 내용에 만족하셨습니까', '180건', '4.4', '매우 만족 110 · 만족 55 · 보통 15 · 불만족 0'],
      ['시설 이용이 편리했습니까', '0건', '산출 안 함', '-'],
    ]);
    expect(screen.getByText(/응답자 180명/)).toBeInTheDocument();
  });
});