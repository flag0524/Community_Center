// 머리글·전체 메뉴·글자 크기·화면 전환·임시 화면 같은 공통 틀의 동작을 확인하는 시험
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp, useMockServer } from '../test/render';

useMockServer();

describe('전체 메뉴', () => {
  it('버튼을 누르면 열리고 메뉴 다섯 묶음을 보여 주며 닫기 버튼으로 닫힌다', async () => {
    renderApp('/');
    const dialog = document.getElementById('all-menu') as HTMLDialogElement;
    expect(dialog).not.toHaveAttribute('open');

    await userEvent.click(screen.getByRole('button', { name: '전체 메뉴 열기' }));
    expect(dialog).toHaveAttribute('open');
    const tree = within(dialog).getByRole('navigation', { name: '전체 메뉴 트리' });
    expect(within(tree).getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual([
      '강좌정보',
      '강사은행',
      '커뮤니티',
      '센터소개',
      '마이페이지',
    ]);

    await userEvent.click(within(dialog).getByRole('button', { name: '전체 메뉴 닫기' }));
    expect(dialog).not.toHaveAttribute('open');
  });

  it('어두운 바깥 영역을 누르면 닫히고 안쪽 내용을 눌러서는 닫히지 않는다', async () => {
    renderApp('/');
    const dialog = document.getElementById('all-menu') as HTMLDialogElement;

    await userEvent.click(screen.getByRole('button', { name: '전체 메뉴 열기' }));
    await userEvent.click(within(dialog).getByRole('heading', { name: '커뮤니티' }));
    expect(dialog).toHaveAttribute('open');

    await userEvent.click(dialog);
    expect(dialog).not.toHaveAttribute('open');
  });

  it('메뉴 링크를 누르면 이동하고 대화상자가 닫힌다', async () => {
    const { router } = renderApp('/');
    const dialog = document.getElementById('all-menu') as HTMLDialogElement;

    await userEvent.click(screen.getByRole('button', { name: '전체 메뉴 열기' }));
    await userEvent.click(within(dialog).getByRole('link', { name: '시설안내' }));

    expect(router.state.location.pathname).toBe('/center/facility');
    expect(dialog).not.toHaveAttribute('open');
  });
});

describe('글자 크기', () => {
  it('한 단계씩 키우고 줄이며 끝에서는 버튼이 비활성화된다', async () => {
    renderApp('/');
    const bigger = screen.getByRole('button', { name: '글자 크게' });
    const smaller = screen.getByRole('button', { name: '글자 작게' });

    await userEvent.click(bigger);
    await userEvent.click(bigger);
    expect(document.documentElement.style.fontSize).toBe('120%');
    expect(bigger).toBeDisabled();
    expect(screen.getByText('글자 크기 120%')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '글자 크기 기본으로' }));
    expect(document.documentElement.style.fontSize).toBe('100%');
    expect(bigger).toBeEnabled();

    await userEvent.click(smaller);
    expect(document.documentElement.style.fontSize).toBe('90%');
    expect(smaller).toBeDisabled();
  });

  it('조절한 크기를 세션에 기억한다', async () => {
    renderApp('/');
    await userEvent.click(screen.getByRole('button', { name: '글자 크게' }));
    expect(sessionStorage.getItem('text-size')).toBe('110');
  });

  it('세션에 기억한 크기로 시작한다', () => {
    sessionStorage.setItem('text-size', '90');
    renderApp('/');
    expect(document.documentElement.style.fontSize).toBe('90%');
  });
});

describe('화면 선택', () => {
  it('기본 화면으로 시작하고 현재 화면을 aria-current로 알린다', () => {
    renderApp('/');
    expect(document.documentElement.dataset.view).toBe('standard');
    expect(screen.getByRole('link', { name: '기본 화면' })).toHaveAttribute('aria-current', 'true');
    expect(screen.getByRole('link', { name: '쉬운 화면' })).toHaveAttribute('aria-current', 'false');
  });

  it('쉬운 화면을 고르면 주소와 html 속성과 세션이 바뀌고 글자가 25% 커진다', async () => {
    const { router } = renderApp('/');
    await userEvent.click(screen.getByRole('link', { name: '쉬운 화면' }));

    expect(router.state.location.search).toBe('?view=easy');
    expect(document.documentElement.dataset.view).toBe('easy');
    expect(sessionStorage.getItem('view')).toBe('easy');
    expect(document.documentElement.style.fontSize).toBe('125%');
    expect(screen.getByRole('link', { name: '쉬운 화면' })).toHaveAttribute('aria-current', 'true');
  });

  it('쉬운 화면에서 다른 화면으로 이동해도 쉬운 화면이 유지된다', async () => {
    const { router } = renderApp('/?view=easy');
    await userEvent.click(screen.getAllByRole('link', { name: '강좌 찾기' })[0]!);

    expect(router.state.location.pathname).toBe('/courses');
    expect(document.documentElement.dataset.view).toBe('easy');
  });

  it('세션에 쉬운 화면이 기억되어 있으면 주소에 없어도 쉬운 화면으로 시작한다', () => {
    sessionStorage.setItem('view', 'easy');
    renderApp('/');
    expect(document.documentElement.dataset.view).toBe('easy');
  });

  it('쉬운 화면에서 글자 크기를 올리면 1.25배에 조절 값을 곱한다', async () => {
    renderApp('/?view=easy');
    await userEvent.click(screen.getByRole('button', { name: '글자 크게' }));
    expect(document.documentElement.style.fontSize).toBe('137.5%');
  });
});

describe('주 메뉴와 검색', () => {
  it('현재 경로가 속한 묶음만 강조한다', () => {
    renderApp('/center/facility');
    const items = screen.getByRole('navigation', { name: '주 메뉴' }).querySelectorAll('.nav-item');
    expect([...items].filter((item) => item.classList.contains('active')).map((i) => i.querySelector('a')?.textContent)).toEqual(['센터소개']);
  });

  it('홈에서는 어느 묶음도 강조하지 않는다', () => {
    renderApp('/');
    expect(document.querySelector('.nav-item.active')).toBeNull();
  });

  it('검색어를 제출하면 강좌 목록 경로로 검색어를 넘긴다', async () => {
    const { router } = renderApp('/');
    await userEvent.type(screen.getByRole('searchbox', { name: '통합 강좌 검색' }), '요가 {Enter}');
    expect(router.state.location.pathname).toBe('/courses');

    expect(router.state.location.pathname).toBe('/courses');
    expect(router.state.location.search).toBe('?q=%EC%9A%94%EA%B0%80');
  });

  it('로그인 링크는 로그인 경로로 간다', () => {
    renderApp('/');
    expect(screen.getByRole('link', { name: '로그인' })).toHaveAttribute('href', '/login');
  });
});

describe('임시 화면과 없는 경로', () => {
  it('아직 옮기지 않은 화면은 안내와 홈 링크를 보이고 문서 제목을 맞춘다', () => {
    renderApp('/board/faq');
    expect(screen.getByRole('heading', { level: 1, name: '자주하는 질문' })).toBeInTheDocument();
    expect(screen.getByText('이 화면은 아직 이식 전입니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '홈으로' })).toHaveAttribute('href', '/');
    expect(document.title).toBe('자주하는 질문 | 조리읍주민자치센터');
  });

  it('메뉴에 있는 모든 경로가 임시 화면으로 연결되어 있다', () => {
    for (const path of ['/board/notice', '/instructors/recruit', '/board/gallery', '/me/profile', '/find-id', '/reset-password']) {
      const { unmount } = renderApp(path);
      expect(screen.queryByText('페이지를 찾을 수 없습니다')).not.toBeInTheDocument();
      expect(screen.getByText('이 화면은 아직 이식 전입니다.')).toBeInTheDocument();
      unmount();
    }
  });

  it('알 수 없는 경로는 찾을 수 없다는 화면을 보인다', () => {
    renderApp('/없는/경로');
    expect(screen.getByRole('heading', { level: 1, name: '페이지를 찾을 수 없습니다' })).toBeInTheDocument();
  });
});

describe('푸터', () => {
  it('연락처 응답으로 주소와 전화번호를 그리고 도로명 주소와 층 안내 사이는 전각 공백으로 띄운다', async () => {
    renderApp('/');
    const footer = screen.getByRole('contentinfo');

    await within(footer).findByText(/봉천로 64/);
    // 테스트 라이브러리는 비교 전에 공백을 정규화하므로 전각 공백은 원문 textContent로 확인한다.
    expect(footer.textContent).toContain('[10937] 경기도 파주시 조리읍 봉천로 64　조리읍 행정복지센터 3층');
    expect(within(footer).getAllByRole('link', { name: '031-941-7742' })[0]).toHaveAttribute('href', 'tel:031-941-7742');
    expect(within(footer).getByRole('link', { name: '031-940-8121' })).toHaveAttribute('href', 'tel:031-940-8121');
    expect(within(footer).getAllByRole('link').map((link) => link.textContent)).toEqual(
      expect.arrayContaining(['개인정보처리방침', '이용약관', '이메일무단수집거부']),
    );
  });
});

describe('접근성 기본기', () => {
  it('본문 바로가기 링크가 첫 번째이고 본문 영역을 가리킨다', () => {
    renderApp('/');
    const links = screen.getAllByRole('link');
    expect(links[0]).toHaveTextContent('본문 바로가기');
    expect(links[0]).toHaveAttribute('href', '#main');
    expect(document.getElementById('main')).not.toBeNull();
  });

  it('문서 언어와 주요 영역 이름이 있다', () => {
    renderApp('/');
    expect(screen.getByRole('navigation', { name: '화면 선택' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '글자 크기 조절' })).toBeInTheDocument();
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
  });
});
