// 강좌 목록(전체·접수중·접수예정)이 서버 응답과 주소의 조건대로 그려지는지 확인하는 시험
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { setMockNow } from '../../mocks/clock';
import { renderApp, useMockServer } from '../../test/render';

useMockServer();

const AFTER = new Date('2026-11-01T10:00:00+09:00'); // 접수 마감 뒤, 교육 중
const DURING = new Date('2026-09-08T10:00:00+09:00'); // 접수 기간
const BEFORE = new Date('2026-08-20T10:00:00+09:00'); // 접수 전

beforeEach(() => setMockNow(AFTER));
afterEach(() => setMockNow(null));

const rows = async () => within(await screen.findByRole('table')).getAllByRole('row').slice(1);

describe('전체 강좌', () => {
  it('첫 쪽에 10건을 그리고 전체 건수와 기수·교육기간을 보인다', async () => {
    renderApp('/courses');

    expect(await rows()).toHaveLength(10);
    expect(screen.getByText('25', { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByText('2026년 4분기 · 교육 10.01 — 12.31')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: '2026년 4분기 강좌 목록' })).toBeInTheDocument();
  });

  it('행에 접수·교육 상태, 분야와 강사, 기간, 일정, 정원, 수강료를 시안대로 쓴다', async () => {
    renderApp('/courses');
    const first = (await rows())[0]!;

    expect(within(first).getByText('접수마감')).toBeInTheDocument();
    expect(within(first).getByText('교육중')).toBeInTheDocument();
    expect(within(first).getByText('컴퓨터 · 추순자')).toBeInTheDocument();
    expect(within(first).getByRole('link', { name: '초급컴퓨터' })).toHaveAttribute('href', '/courses/1');
    expect(first.textContent).toContain('접수　09.07 – 09.11');
    expect(first.textContent).toContain('교육　10.01 – 12.31');
    expect(within(first).getByText('화·목')).toBeInTheDocument();
    expect(within(first).getByText('10:00~11:30')).toBeInTheDocument();
    expect(within(first).getByText('12명')).toBeInTheDocument();
    expect(within(first).getByText('60,000원')).toBeInTheDocument();
  });

  it('접수마감일 때는 잔여석을 숨긴다', async () => {
    renderApp('/courses');
    await rows();
    expect(screen.queryByText(/잔여 \d+석/)).not.toBeInTheDocument();
  });

  it('쪽 번호를 3개 보이고 현재 쪽만 링크가 아니다', async () => {
    renderApp('/courses');
    const pager = await screen.findByRole('navigation', { name: '쪽 이동' });

    expect(within(pager).getByText('1', { exact: false }).closest('strong')).toHaveAttribute('aria-current', 'page');
    // 이름에 보이는 숫자가 낱말로 들어가야 한다(WCAG 2.5.3). '2쪽'이 아니라 '2 쪽'이다.
    expect(within(pager).getByRole('link', { name: '2 쪽' })).toHaveAttribute('href', '/courses?page=2');
    expect(within(pager).getByRole('link', { name: '3 쪽' })).toHaveAttribute('href', '/courses?page=3');
  });

  it('두 번째 쪽은 11번째부터 보인다', async () => {
    renderApp('/courses?page=2');
    const list = await rows();

    expect(list).toHaveLength(10);
    expect(within(list[0]!).getByRole('link', { name: '요가B(초급)' })).toHaveAttribute('href', '/courses/11');
    expect(screen.getByRole('navigation', { name: '쪽 이동' }).querySelector('[aria-current="page"]')?.textContent).toContain('2');
  });

  it('쪽 이동 링크는 걸어 둔 조건을 유지한다', async () => {
    renderApp('/courses?categoryId=4');
    const pager = await screen.findByRole('navigation', { name: '쪽 이동' });
    expect(within(pager).getByRole('link', { name: '2 쪽' })).toHaveAttribute('href', '/courses?categoryId=4&page=2');
  });

  it('강사명 검색 결과를 보이고 강사가 없는 강좌는 시안 문구를 쓴다', async () => {
    renderApp('/courses?q=헬스');
    const list = await rows();

    expect(list).toHaveLength(1);
    expect(within(list[0]!).getByText('생활체육/건강 · 시간표 미기재')).toBeInTheDocument();
    expect(within(list[0]!).getByText('월~금')).toBeInTheDocument();
    expect(within(list[0]!).getByText('180명')).toBeInTheDocument();
  });

  it('요일마다 시간이 다른 강좌와 반이 나뉜 강좌를 두 줄 표기로 보인다', async () => {
    renderApp('/courses?q=한국무용');
    const dance = (await rows())[0]!;
    expect(within(dance).getByText('수·금')).toBeInTheDocument();
    expect(within(dance).getByText('(수)12:00~13:30 / (금)10:00~11:30')).toBeInTheDocument();
  });

  it('요일 조건은 그 요일이 일정에 하나라도 있으면 포함한다', async () => {
    renderApp('/courses?day=FRI&size=50');
    const list = await rows();
    const names = list.map((row) => row.querySelector('.course-name')?.textContent);
    expect(names).toContain('한국무용'); // 금요일 일정이 따로 있다
    expect(names).not.toContain('초급컴퓨터'); // 화·목
  });

  it('조건에 맞는 강좌가 없으면 조건 변경 안내를 보인다', async () => {
    renderApp('/courses?q=없는강좌이름');
    expect(await screen.findByText('검색 조건에 맞는 강좌가 없습니다. 조건을 변경해 주세요.')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    // 조건을 바꿀 수 있도록 검색 폼은 남아 있다.
    expect(screen.getByRole('search', { name: '강좌 검색' })).toBeInTheDocument();
  });

  it('잘못된 쪽 번호나 요일 값은 무시한다', async () => {
    renderApp('/courses?page=abc&day=SUN&categoryId=가나다');
    expect(await rows()).toHaveLength(10);
  });

  it('사이드 메뉴는 현재 항목만 현재 쪽으로 표시하고 문의 전화를 보인다', async () => {
    renderApp('/courses');
    const side = (await screen.findByRole('navigation', { name: '강좌정보 하위 메뉴' })).closest('aside') as HTMLElement;

    expect(within(side).getByRole('link', { name: /전체 강좌/ })).toHaveAttribute('aria-current', 'page');
    expect(within(side).getByRole('link', { name: /접수중 강좌/ })).not.toHaveAttribute('aria-current');
    expect(await within(side).findByRole('link', { name: '031-941-7742' })).toBeInTheDocument();
  });

  it('현재 위치와 히어로 제목을 보인다', async () => {
    renderApp('/courses');
    await rows();
    const crumbs = screen.getByRole('navigation', { name: '현재 위치' });
    expect(within(crumbs).getByRole('link', { name: '홈' })).toHaveAttribute('href', '/');
    expect(within(crumbs).getByText('전체 강좌').tagName).toBe('STRONG');
    expect(document.title).toBe('전체 강좌 | 조리읍주민자치센터');
  });
});

describe('접수중·접수예정 강좌', () => {
  it('접수 기간이면 접수중 강좌를 모두 보이고 정원 아래에 잔여석을 보인다', async () => {
    setMockNow(DURING);
    renderApp('/courses/open');
    const list = await rows();

    expect(list).toHaveLength(10);
    expect(within(list[0]!).getAllByText('접수중')[0]).toBeInTheDocument();
    expect(within(list[0]!).getByText('교육예정')).toBeInTheDocument();
    // 정원 12명의 60%(7명)가 찼다고 보는 시험용 값이라 5석이 남는다.
    // 쉬운 화면은 시안 CSS가 정원 칸을 숨기므로(C2) 접수 상태 칸에 같은 문구를 쉬운 화면 전용으로 한 번 더 둔다.
    const seatTexts = within(list[0]!).getAllByText('잔여 5석');
    expect(seatTexts).toHaveLength(2);
    expect(seatTexts.map((node) => node.closest('td')?.dataset.label ?? 'status')).toEqual(['status', '정원']);
    expect(seatTexts[0]!).toHaveClass('easy-only');
    expect(seatTexts[1]!).not.toHaveClass('easy-only');
    expect(screen.getByText('25', { selector: 'strong' })).toBeInTheDocument();
  });

  it('접수중이 아닌 강좌는 쉬운 화면용 잔여석 문구도 없다', async () => {
    renderApp('/courses');
    const list = await rows();
    expect(within(list[0]!).queryByText(/잔여/)).not.toBeInTheDocument();
  });

  it('접수 기간이 아니면 접수중 강좌 빈 상태를 안내하고 전체 강좌로 보낸다', async () => {
    renderApp('/courses/open');
    expect(await screen.findByRole('heading', { name: '현재 확인된 접수중 강좌가 없습니다.' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '전체 강좌 보기' })).toHaveAttribute('href', '/courses');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByRole('search', { name: '강좌 검색' })).not.toBeInTheDocument();
  });

  it('접수 전이면 접수예정 강좌를 접수예정·교육예정으로 보인다', async () => {
    setMockNow(BEFORE);
    renderApp('/courses/upcoming');
    const list = await rows();

    expect(within(list[0]!).getByText('접수예정')).toBeInTheDocument();
    expect(within(list[0]!).getByText('교육예정')).toBeInTheDocument();
    expect(within(list[0]!).queryByText(/잔여/)).not.toBeInTheDocument();
  });

  it('접수예정 강좌가 없으면 그 상태에 맞는 빈 상태를 보인다', async () => {
    renderApp('/courses/upcoming');
    expect(await screen.findByRole('heading', { name: '현재 확인된 접수예정 강좌가 없습니다.' })).toBeInTheDocument();
  });
});

describe('검색 조건 적용', () => {
  it('기본 화면에서는 분야를 고르는 즉시 주소에 반영한다', async () => {
    const { router } = renderApp('/courses');
    await rows();

    await screen.findByRole('option', { name: '생활체육/건강' });
    await userEvent.selectOptions(screen.getByRole('combobox', { name: '관심 분야' }), '3');
    expect(router.state.location.pathname).toBe('/courses');
    expect(router.state.location.search).toBe('?categoryId=3');
    expect(await rows()).toHaveLength(9);
  });

  it('쉬운 화면에서는 분야를 골라도 강좌 찾기 버튼을 눌러야 반영한다', async () => {
    const { router } = renderApp('/courses?view=easy');
    await rows();

    await screen.findByRole('option', { name: '생활체육/건강' });
    await userEvent.selectOptions(screen.getByRole('combobox', { name: '관심 분야' }), '3');
    expect(router.state.location.search).toBe('?view=easy');

    await userEvent.click(screen.getByRole('button', { name: '강좌 찾기' }));
    expect(router.state.location.search).toBe('?categoryId=3');
    expect(await rows()).toHaveLength(9);
  });

  it('검색어는 제출할 때 반영하고 쪽은 1로 돌아간다', async () => {
    const { router } = renderApp('/courses?page=2');
    await rows();

    await userEvent.type(screen.getByRole('searchbox', { name: '강좌명·강사명' }), '요가{Enter}');
    expect(router.state.location.search).toBe('?q=%EC%9A%94%EA%B0%80');
    expect(await rows()).toHaveLength(2);
  });

  it('조건 지우기는 모든 조건을 비우고 입력 칸도 비운다', async () => {
    const { router } = renderApp('/courses?q=요가&categoryId=3&day=TUE');
    await rows();
    expect(screen.getByRole('searchbox', { name: '강좌명·강사명' })).toHaveValue('요가');

    await userEvent.click(screen.getByRole('button', { name: '조건 지우기' }));
    expect(router.state.location.search).toBe('');
    expect(screen.getByRole('searchbox', { name: '강좌명·강사명' })).toHaveValue('');
    expect(screen.getByRole('combobox', { name: '관심 분야' })).toHaveValue('');
    expect(await rows()).toHaveLength(10);
  });

  it('분야 선택지는 서버가 준 분야 목록이고 요일은 월~금이다', async () => {
    renderApp('/courses');
    await rows();
    await screen.findByRole('option', { name: '문화/취미' });
    const category = screen.getByRole('combobox', { name: '관심 분야' });
    expect(within(category).getAllByRole('option').map((o) => o.textContent)).toEqual([
      '전체 분야',
      '컴퓨터',
      '어학/교양',
      '생활체육/건강',
      '문화/취미',
    ]);
    const day = screen.getByRole('combobox', { name: '요일' });
    expect(within(day).getAllByRole('option').map((o) => o.textContent)).toEqual(['전체 요일', '월', '화', '수', '목', '금']);
  });
});

describe('쉬운 화면 전용 요소', () => {
  it('처음 화면 링크, 이용 순서, 안내 문장, 자세히 보기 열이 있다', async () => {
    renderApp('/courses?view=easy');
    const list = await rows();

    expect(screen.getByRole('link', { name: '← 처음 화면으로' })).toHaveAttribute('href', '/');
    const path = screen.getByRole('list', { name: '강좌 이용 순서' });
    expect(within(path).getAllByRole('listitem')).toHaveLength(3);
    expect(within(path).getByText('강좌 찾기').closest('li')).toHaveAttribute('aria-current', 'step');
    expect(
      screen.getByText((_, element) => element?.tagName === 'P' && /강좌 찾기를 눌러 주세요/.test(element.textContent ?? '')),
    ).toBeInTheDocument();
    // 이름은 화면에 보이는 글자를 낱말 단위로 포함하고 어느 강좌인지만 덧붙인다(WCAG 2.5.3).
    const more = within(list[0]!).getByRole('link', { name: '이 강좌 자세히 보기 (초급컴퓨터)' });
    expect(more).toHaveAttribute('href', '/courses/1');
    expect(more.textContent).toBe('이 강좌 자세히 보기');
  });
});
