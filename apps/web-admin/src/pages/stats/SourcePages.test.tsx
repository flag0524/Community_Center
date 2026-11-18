// 연령·성별 집계자료(목록, 권한, 등록 양식의 검증과 등록, 상세, 승인·반려 두 번 확인)를 확인하는 시험
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);
const SRC = (n: number) => `93${String(n).padStart(20, '0')}`;
const fact = (name: string) => screen.getByText(name, { selector: 'dt' }).nextElementSibling?.textContent;
const fill = async (label: string, value: string) => {
  const field = screen.getByLabelText(/^[0-9]+행 /.test(label) ? label : new RegExp(`^${label}`)); // 필수 표시(*)가 이름표에 붙는다
  await userEvent.clear(field);
  await userEvent.type(field, value);
};
const fillRow = async (n: number, values: Record<string, string>) => {
  for (const [label, value] of Object.entries(values)) await fill(`${n}행 ${label}`, value);
};
const fillHead = async (overrides: Record<string, string> = {}) => {
  const values = { '출처 기관': '파주시 통계', '근거 식별자': '문서-2026-9', '계열 키': 'age-gender-2027', '모집단·중복 처리 기준': '만 나이', ...overrides };
  for (const [label, value] of Object.entries(values)) await fill(label, value);
  await fill('집계 기간 시작', '2027-01-01');
  await fill('집계 기간 끝', '2027-06-30');
  await fill('연령 기준일', '2027-06-30');
};

describe('집계자료 목록', () => {
  it('버전·출처·기간·기준일·상태를 최근 등록 순으로 보이고 등록 담당자에게 등록 버튼을 보인다', async () => {
    await signInAs('group');
    renderApp('/stats-sources');
    expect(await heading('연령·성별 집계자료')).toBeInTheDocument();
    const [first, second] = await rows('집계자료 목록');
    expect(cells(first!).slice(0, 6)).toEqual(['age-gender-2026', '2', '파주시 주민등록 통계', '2026-01-01 ~ 2026-10-31', '2026-10-31', '검토 대기']);
    expect(cells(second!).slice(0, 6)).toEqual(['age-gender-2026', '1', '파주시 주민등록 통계', '2026-01-01 ~ 2026-10-31', '2026-10-31', '승인']);
    expect(screen.getByRole('link', { name: '집계자료 등록' })).toHaveAttribute('href', '/stats-sources/new');
  });

  it('메뉴에 보이고 등록·승인 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('group');
    const first = renderApp('/stats-sources');
    expect(await within(await screen.findByRole('navigation', { name: '운영 현황 하위 메뉴' })).findByRole('link', { name: '연령·성별 집계자료' })).toBeInTheDocument();
    first.unmount();
    await signInAs('course');
    renderApp('/stats-sources');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('집계자료 상세와 승인·반려', () => {
  it('입력한 표와 출처·기준을 그대로 보인다', async () => {
    await signInAs('group');
    renderApp(`/stats-sources/${SRC(1)}`);
    expect(await heading('집계자료 상세')).toBeInTheDocument();
    expect(fact('버전')).toBe('1');
    expect(fact('상태')).toBe('승인');
    expect(fact('모집단·중복 처리 기준')).toBe('만 나이, 중복 거주 제외');
    expect((await rows('집계 표')).map((row) => cells(row))).toEqual([
      ['20~29세', '20', '29', '남', '120명'],
      ['20~29세', '20', '29', '여', '150명'],
      ['80세 이상', '80', '-', '미상', '0명'],
    ]);
    expect(screen.queryByRole('button', { name: /승인/ })).not.toBeInTheDocument(); // 승인한 자료는 다시 결정하지 않는다
  });

  it('검토 대기 자료는 두 번 확인해 승인하고 결정한 담당자를 보인다', async () => {
    await signInAs('group');
    renderApp(`/stats-sources/${SRC(2)}`);
    await heading('집계자료 상세');
    await userEvent.click(await screen.findByRole('button', { name: '승인 (age-gender-2026 버전 2)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 승인 (age-gender-2026 버전 2)' }));
    expect(await screen.findByText('승인', { selector: 'dd' })).toBeInTheDocument();
    expect(fact('결정')).toContain('김관리');
    expect(screen.queryByRole('button', { name: /승인 \(/ })).not.toBeInTheDocument();
  });

  it('반려하면 반려 상태가 된다', async () => {
    await signInAs('group');
    renderApp(`/stats-sources/${SRC(2)}`);
    await heading('집계자료 상세');
    await userEvent.click(await screen.findByRole('button', { name: '반려 (age-gender-2026 버전 2)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 반려 (age-gender-2026 버전 2)' }));
    expect(await screen.findByText('반려', { selector: 'dd' })).toBeInTheDocument();
  });

  it('없는 자료는 오류를 알린다', async () => {
    await signInAs('group');
    renderApp(`/stats-sources/${SRC(99)}`);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});

describe('집계자료 등록', () => {
  it('필수 값이 비었거나 인원이 숫자가 아니면 보내지 않고 알린다', async () => {
    await signInAs('group');
    renderApp('/stats-sources/new');
    await heading('집계자료 등록');
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    expect((await screen.findAllByText('필수 항목입니다.')).length).toBe(7);
    expect(screen.getByText('구간·성별 분류의 식별자와 이름은 필수입니다.')).toBeInTheDocument();
    await fillHead();
    await fillRow(1, { '연령구간 식별자': 'a20', '연령구간 이름': '20~29세', '성별 식별자': 'M', '성별 이름': '남', 인원: '열' });
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(await screen.findByText('인원은 0 이상의 정수입니다.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: '집계자료 등록' })).toBeInTheDocument();
  });

  it('입력한 표를 등록하면 검토 대기 상세로 이동하고 다음 버전이 매겨진다', async () => {
    await signInAs('group');
    renderApp('/stats-sources/new');
    await heading('집계자료 등록');
    await fillHead({ '계열 키': 'age-gender-2026' }); // 같은 계열이라 다음 버전이 된다
    await fillRow(1, { '연령구간 식별자': 'a20', '연령구간 이름': '20~29세', 하한: '20', 상한: '29', '성별 식별자': 'M', '성별 이름': '남', 인원: '7' });
    await userEvent.click(screen.getByRole('button', { name: '행 추가' }));
    await fillRow(2, { '연령구간 식별자': 'a80', '연령구간 이름': '80세 이상', 하한: '80', '성별 식별자': 'U', '성별 이름': '미상', 인원: '0' });
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(await heading('집계자료 상세')).toBeInTheDocument();
    expect(fact('버전')).toBe('3');
    expect(fact('상태')).toBe('검토 대기');
    expect((await rows('집계 표')).map((row) => cells(row))).toEqual([
      ['20~29세', '20', '29', '남', '7명'],
      ['80세 이상', '80', '-', '미상', '0명'],
    ]);
  });

  it('서버가 거절한 기간 오류와 중복 조합 오류를 알린다', async () => {
    await signInAs('group');
    renderApp('/stats-sources/new');
    await heading('집계자료 등록');
    await fillHead();
    await fill('집계 기간 끝', '2026-12-31');
    await fillRow(1, { '연령구간 식별자': 'a20', '연령구간 이름': '20~29세', '성별 식별자': 'M', '성별 이름': '남', 인원: '7' });
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(await screen.findByText('집계 기간의 끝은 시작보다 빠를 수 없습니다.')).toBeInTheDocument();
    await fill('집계 기간 끝', '2027-06-30');
    await userEvent.click(screen.getByRole('button', { name: '행 추가' }));
    await fillRow(2, { '연령구간 식별자': 'a20', '연령구간 이름': '20~29세', '성별 식별자': 'M', '성별 이름': '남', 인원: '1' });
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(await screen.findByText('같은 연령구간·성별 분류가 두 번 들어 있습니다.')).toBeInTheDocument();
  });

  it('행을 지울 수 있고 한 행만 남으면 지울 수 없다', async () => {
    await signInAs('group');
    renderApp('/stats-sources/new');
    await heading('집계자료 등록');
    expect(screen.getByRole('button', { name: '1행 삭제' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '행 추가' }));
    expect(screen.getByLabelText('2행 인원')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '2행 삭제' }));
    expect(screen.queryByLabelText('2행 인원')).not.toBeInTheDocument();
  });
});
