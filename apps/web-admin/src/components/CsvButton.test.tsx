// CSV 내려받기 버튼과 모의 CSV 응답의 조건 반영, BOM·수식 방지, 오류 안내, 작업이력을 확인하는 시험
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { csvResponse, EXPORT_MAX_ROWS, exportLog } from '../mocks/csv';
import { renderApp, server, signInAs, useMockServer } from '../test/render';

useMockServer();

let saved: { blob: Blob; name: string }[] = [];
let blobOf: Blob | null = null;

beforeEach(() => {
  saved = [];
  blobOf = null;
  URL.createObjectURL = vi.fn((blob: Blob | MediaSource) => {
    blobOf = blob as Blob;
    return 'blob:test';
  });
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    saved.push({ blob: blobOf!, name: this.download });
  });
});

afterEach(() => vi.restoreAllMocks());

// text()는 BOM을 떼고 읽으므로 바이트로 확인한다
const hasBom = async (blob: Blob) => [...new Uint8Array(await blob.arrayBuffer()).slice(0, 3)].join() === '239,187,191';

const csvButton = () => screen.findByRole('button', { name: 'CSV 내려받기' });

describe('CSV 내려받기 버튼', () => {
  it('현재 조회 조건 그대로 만든 파일을 서버가 정한 이름으로 저장하고 작업이력을 남긴다', async () => {
    await signInAs('group');
    renderApp('/pay/applications?status=WAITING');
    await userEvent.click(await csvButton());
    await waitFor(() => expect(saved.length).toBe(1));
    expect(saved[0]!.name).toBe('applications.csv');
    const text = await saved[0]!.blob.text();
    const lines = text.split('\r\n').filter(Boolean);
    expect(text.startsWith('신청번호,강좌')).toBe(true);
    expect(await hasBom(saved[0]!.blob)).toBe(true);
    expect(lines.length).toBe(1 + 3);
    expect(exportLog).toEqual([{ name: 'applications.csv', rows: 3 }]);
  });

  it('조건이 없으면 목록 전체를 담고 이름은 가려진 채로 담는다', async () => {
    await signInAs('group');
    renderApp('/pay/applications');
    await userEvent.click(await csvButton());
    await waitFor(() => expect(saved.length).toBe(1));
    const text = await saved[0]!.blob.text();
    expect(text.split('\r\n').filter(Boolean).length).toBe(1 + 11);
    expect(text).toContain('오○○');
  });

  it('서버가 거절하면 사유를 알리고 파일을 저장하지 않는다', async () => {
    await signInAs('group');
    renderApp('/pay/applications');
    server.use(
      http.get('/api/admin/v1/applications/export.csv', () =>
        HttpResponse.json(
          { code: 'RULE_REJECTED', message: '내려받을 행이 5만 건을 넘습니다. 조건을 좁혀 주세요.', fields: null, requestId: 'x' },
          { status: 422 },
        ),
      ),
    );
    await userEvent.click(await csvButton());
    expect(await screen.findByRole('alert')).toHaveTextContent('5만 건을 넘습니다');
    expect(saved).toEqual([]);
  });
});

describe('모의 CSV 응답', () => {
  it('쉼표·따옴표·줄바꿈은 따옴표로 감싸고 수식으로 읽힐 문자열은 앞에 작은따옴표를 붙인다', async () => {
    const response = csvResponse('t.csv', ['a', 'b'], [['=SUM(1)', 'x,"y"'], ['-3', -3], [null, '줄\n바꿈']], ['조건 메모']);
    const text = await response.text();
    expect(text).toBe('# 조건 메모\r\na,b\r\n\'=SUM(1),"x,""y"""\r\n\'-3,-3\r\n,"줄\n바꿈"\r\n');
  });

  it('5만 행을 넘으면 거절하고 작업이력을 남기지 않는다', async () => {
    const rows = Array.from({ length: EXPORT_MAX_ROWS + 1 }, () => ['x']);
    const response = csvResponse('t.csv', ['a'], rows);
    expect(response.status).toBe(422);
    expect(exportLog).toEqual([]);
    expect(csvResponse('t.csv', ['a'], rows.slice(1)).status).toBe(200);
  });
});

describe('목록·통계별 내려받기', () => {
  const download = async (path: string, button = 'CSV 내려받기') => {
    await signInAs('group');
    renderApp(path);
    await userEvent.click(await screen.findByRole('button', { name: button }));
    await waitFor(() => expect(saved.length).toBe(1));
    return { name: saved[0]!.name, lines: (await saved[0]!.blob.text()).split('\r\n').filter(Boolean) };
  };

  it('결제·거래는 충돌 통보 탭 조건을 그대로 넘긴다', async () => {
    const all = await download('/pay/transactions');
    expect(all.name).toBe('transactions.csv');
    expect(all.lines.length).toBe(1 + 6);
    expect(all.lines[0]).toBe('주문번호,신청번호,결제수단,결제상태,금액,요청시각,승인시각,재조회 횟수,충돌 통보');
  });

  it('결제·거래 충돌 통보 탭에서는 충돌 건만 담는다', async () => {
    const conflict = await download('/pay/transactions?tab=conflict');
    expect(conflict.lines.length).toBe(1 + 1);
    expect(conflict.lines[1]).toContain('충돌');
  });

  it('환불은 계좌 같은 민감 값 없이 목록 조건만 담는다', async () => {
    const refunds = await download('/pay/refunds');
    expect(refunds.name).toBe('refunds.csv');
    expect(refunds.lines[0]).toBe('환불번호,신청번호,강좌,신청금액,상태,접수 주체,접수일,경과 영업일,기한');
    expect(refunds.lines.join('')).not.toMatch(/계좌|account/i);
  });

  it('수요 통계는 집계 조건을 주석 행으로 먼저 적고 분야 조건을 반영한다', async () => {
    const demand = await download('/stats?tab=demand&categoryId=5000000000000000000003');
    expect(demand.lines[0]).toBe('# 수요 통계');
    expect(demand.lines[1]).toContain('조건 기수 전체');
    expect(demand.lines[2]).toMatch(/^# 집계 기준 /);
    expect(demand.lines.length).toBe(3 + 1 + 1);
  });

  it('정산 통계는 확인 중 금액을 순수납과 다른 줄로 둔다', async () => {
    const settlement = await download('/stats?tab=settlement');
    expect(settlement.lines.at(-1)).toBe('확인 중(순수납 제외),,,,120000');
    expect(settlement.lines.some((line) => line.startsWith('CARD,5000000,300000,4700000'))).toBe(true);
  });

  it('연령·성별은 자료 버전과 기준일을 주석 행에 넣는다', async () => {
    const age = await download('/stats?tab=age');
    expect(age.name).toBe('age-gender-stats.csv');
    expect(age.lines.slice(0, 5)).toEqual(['# 연령·성별 통계', '# 자료 버전 2026-상반기 v2', '# 제공 기관 파주시 행정복지센터', '# 기간 2026-01-01 ~ 2026-06-30', '# 기준일 2026-06-30']);
  });

  it('출석과 만족도 탭에는 내려받기 버튼이 없다', async () => {
    await signInAs('group');
    for (const tab of ['attendance', 'satisfaction']) {
      const view = renderApp(`/stats?tab=${tab}`);
      await screen.findByRole('region', { name: tab === 'attendance' ? '출석 탭' : '만족도 탭' });
      await screen.findByText(/집계 기준/);
      expect(screen.queryByRole('button', { name: 'CSV 내려받기' })).toBeNull();
      view.unmount();
    }
  });
});