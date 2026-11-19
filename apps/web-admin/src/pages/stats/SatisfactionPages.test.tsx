// 강좌 만족도 집계자료(목록, 권한, 등록 양식의 검증·문항 편집·등록, 상세, 승인·반려 두 번 확인)를 확인하는 시험
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockCourseIds, mockCourseName } from '../../mocks/education';
import { renderApp, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);
const SRC = (n: number) => `96${String(n).padStart(20, '0')}`;
const COURSE = () => mockCourseName(mockCourseIds()[0] ?? '');
const fact = (name: string) => screen.getByText(name, { selector: 'dt' }).nextElementSibling?.textContent;
const fill = async (label: string, value: string) => {
  const field = screen.getByLabelText(/^[0-9]+번 문항 /.test(label) ? label : new RegExp(`^${label}`)); // 필수 표시(*)가 이름표에 붙는다
  await userEvent.clear(field);
  await userEvent.type(field, value);
};
const fillHead = async () => {
  await userEvent.selectOptions(await screen.findByLabelText(/^강좌/), COURSE());
  await fill('출처 기관', '센터 만족도 조사');
  await fill('근거 식별자', '조사-2027-01');
  await fill('계열 키', 'dgstfn-2027');
  await fill('조사 기간 시작', '2027-01-01');
  await fill('조사 기간 끝', '2027-01-31');
  await fill('전체 응답자 수', '12');
  await fill('집계 기준', '수강생 전수조사');
};
const fillQuestion = async (respondents: string, counts: [string, string]) => {
  await fill('1번 문항 식별자', 'q1');
  await fill('1번 문항 이름', '수강 동기');
  await fill('1번 문항 유효응답자 수', respondents);
  await fill('1번 문항 집계 기준', '단일선택 유효 응답');
  await fill('1번 문항 1번 선택 식별자', 'a');
  await fill('1번 문항 1번 선택 이름', '취미');
  await fill('1번 문항 1번 선택 응답 수', counts[0]);
  await userEvent.click(screen.getByRole('button', { name: '1번 문항 선택 항목 추가' }));
  await fill('1번 문항 2번 선택 식별자', 'b');
  await fill('1번 문항 2번 선택 이름', '취업');
  await fill('1번 문항 2번 선택 응답 수', counts[1]);
};

describe('만족도 집계자료 목록', () => {
  it('강좌·버전·출처·조사 기간·응답자·상태를 최근 등록 순으로 보이고 등록 담당자에게 등록 버튼을 보인다', async () => {
    await signInAs('group');
    renderApp('/satisfaction-sources');
    expect(await heading('강좌 만족도 집계자료')).toBeInTheDocument();
    const [first, second] = await rows('만족도 집계자료 목록');
    expect(cells(first!).slice(0, 7)).toEqual([COURSE(), 'dgstfn-2026', '2', '센터 만족도 조사', '2026-09-01 ~ 2026-10-15', '12명', '검토 대기']);
    expect(cells(second!).slice(0, 7)).toEqual([COURSE(), 'dgstfn-2026', '1', '센터 만족도 조사', '2026-09-01 ~ 2026-10-15', '12명', '승인']);
    expect(screen.getByRole('link', { name: '집계자료 등록' })).toHaveAttribute('href', '/satisfaction-sources/new');
  });

  it('메뉴에 보이고 등록·승인 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('group');
    const first = renderApp('/satisfaction-sources');
    expect(await within(await screen.findByRole('navigation', { name: '운영 현황 하위 메뉴' })).findByRole('link', { name: '강좌 만족도 집계자료' })).toBeInTheDocument();
    first.unmount();
    await signInAs('course');
    renderApp('/satisfaction-sources');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('만족도 집계자료 상세와 승인·반려', () => {
  it('문항별 선택 집계와 점수 범위를 그대로 보인다', async () => {
    await signInAs('group');
    renderApp(`/satisfaction-sources/${SRC(1)}`);
    expect(await heading('만족도 집계자료 상세')).toBeInTheDocument();
    expect(fact('버전')).toBe('1');
    expect(fact('전체 응답자')).toBe('12명');
    expect(fact('집계 기준')).toBe('수강생 전수조사');
    expect((await rows('수강 동기 선택 집계')).map((row) => cells(row))).toEqual([['취미', '7명', '-'], ['취업', '3명', '-']]);
    expect((await rows('강의 만족도 선택 집계')).map((row) => cells(row))).toEqual([['매우 만족', '6명', '5'], ['보통', '3명', '3'], ['무응답', '1명', '-']]);
    expect(screen.getByText(/점수 범위 1~5/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /승인/ })).not.toBeInTheDocument(); // 승인한 자료는 다시 결정하지 않는다
  });

  it('검토 대기 자료는 두 번 확인해 승인하고 결정한 담당자를 보인다', async () => {
    await signInAs('group');
    renderApp(`/satisfaction-sources/${SRC(2)}`);
    await heading('만족도 집계자료 상세');
    const target = `${COURSE()} dgstfn-2026 버전 2`;
    await userEvent.click(await screen.findByRole('button', { name: `승인 (${target})` }));
    await userEvent.click(screen.getByRole('button', { name: `정말 승인 (${target})` }));
    expect(await screen.findByText('승인', { selector: 'dd' })).toBeInTheDocument();
    expect(fact('결정')).toContain('김관리');
    expect(screen.queryByRole('button', { name: /^승인 \(/ })).not.toBeInTheDocument();
  });

  it('반려하면 반려 상태가 된다', async () => {
    await signInAs('group');
    renderApp(`/satisfaction-sources/${SRC(2)}`);
    await heading('만족도 집계자료 상세');
    const target = `${COURSE()} dgstfn-2026 버전 2`;
    await userEvent.click(await screen.findByRole('button', { name: `반려 (${target})` }));
    await userEvent.click(screen.getByRole('button', { name: `정말 반려 (${target})` }));
    expect(await screen.findByText('반려', { selector: 'dd' })).toBeInTheDocument();
  });

  it('없는 자료는 오류를 알린다', async () => {
    await signInAs('group');
    renderApp(`/satisfaction-sources/${SRC(99)}`);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});

describe('만족도 집계자료 등록', () => {
  it('필수 값이 비었거나 응답 수가 숫자가 아니면 보내지 않고 알린다', async () => {
    await signInAs('group');
    renderApp('/satisfaction-sources/new');
    await heading('만족도 집계자료 등록');
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    expect((await screen.findAllByText('필수 항목입니다.')).length).toBe(8);
    expect(screen.getByText('문항 식별자·이름·집계 기준은 필수입니다.')).toBeInTheDocument();
    await fillHead();
    await fillQuestion('10', ['7', '열']);
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(await screen.findByText('선택 응답 수는 0 이상의 정수입니다.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: '만족도 집계자료 등록' })).toBeInTheDocument();
  });

  it('입력한 문항을 등록하면 검토 대기 상세로 이동하고 같은 강좌·계열이라 다음 버전이 매겨진다', async () => {
    await signInAs('group');
    renderApp('/satisfaction-sources/new');
    await heading('만족도 집계자료 등록');
    await fillHead();
    await fill('계열 키', 'dgstfn-2026'); // 시안의 1·2 버전과 같은 계열
    await fill('근거 식별자', '조사-2027-01');
    await fillQuestion('10', ['7', '3']);
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(await heading('만족도 집계자료 상세')).toBeInTheDocument();
    expect(fact('버전')).toBe('3');
    expect(fact('상태')).toBe('검토 대기');
    expect((await rows('수강 동기 선택 집계')).map((row) => cells(row))).toEqual([['취미', '7명', '-'], ['취업', '3명', '-']]);
  });

  it('서버가 거절한 합계 오류를 문항 아래에 알린다', async () => {
    await signInAs('group');
    renderApp('/satisfaction-sources/new');
    await heading('만족도 집계자료 등록');
    await fillHead();
    await fillQuestion('10', ['7', '2']); // 합계 9가 유효응답자 수 10과 다르다
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(await screen.findByText('선택 수의 합이 문항 유효응답자 수와 같아야 합니다.')).toBeInTheDocument();
  });

  it('점수 문항을 고르면 최소·최대 점수와 선택 항목의 점수 칸이 나타난다', async () => {
    await signInAs('group');
    renderApp('/satisfaction-sources/new');
    await heading('만족도 집계자료 등록');
    expect(screen.queryByLabelText('1번 문항 최소 점수')).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('1번 문항 유형'), '점수');
    expect(screen.getByLabelText('1번 문항 최소 점수')).toBeInTheDocument();
    expect(screen.getByLabelText('1번 문항 1번 선택 점수')).toBeInTheDocument();
  });

  it('문항과 선택 항목을 더하고 지울 수 있고 하나만 남으면 지울 수 없다', async () => {
    await signInAs('group');
    renderApp('/satisfaction-sources/new');
    await heading('만족도 집계자료 등록');
    expect(screen.getByRole('button', { name: '1번 문항 삭제' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '1번 문항 1번 선택 삭제' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '문항 추가' }));
    expect(screen.getByLabelText('2번 문항 식별자')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '2번 문항 삭제' }));
    expect(screen.queryByLabelText('2번 문항 식별자')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '1번 문항 선택 항목 추가' }));
    await userEvent.click(screen.getByRole('button', { name: '1번 문항 2번 선택 삭제' }));
    expect(screen.queryByLabelText('1번 문항 2번 선택 이름')).not.toBeInTheDocument();
  });
});
