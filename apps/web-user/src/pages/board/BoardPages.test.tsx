// 공지사항·기관소식·자료실·센터 갤러리·자주하는 질문의 목록과 게시물 상세가 서버 응답대로 그려지는지 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp, server, useMockServer } from '../../test/render';

useMockServer();

const user = () => userEvent.setup({ delay: null });
const crumbs = () => within(screen.getByRole('navigation', { name: '현재 위치' }));
const NOTICE_TITLE = '2026년 4분기 조리읍주민자치센터 수강생 모집';

describe('공지사항', () => {
  it('히어로 제목, 현재 위치, 검색 양식과 상단공지를 구분해 보이는 표를 그린다', async () => {
    renderApp('/board/notice');

    expect(await screen.findByRole('heading', { level: 1, name: '공지사항' })).toBeInTheDocument();
    expect(crumbs().getByText('커뮤니티')).toBeInTheDocument();
    expect(crumbs().getByText('공지사항').tagName).toBe('STRONG');
    const menu = screen.getByRole('navigation', { name: '커뮤니티 하위 메뉴' });
    expect(within(menu).getByRole('link', { name: /공지사항/ })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('search', { name: '공지사항 검색' })).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: '공지사항 목록' });
    expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['구분', '제목', '등록일']);
    const first = within(table).getAllByRole('row')[1]!;
    expect(within(first).getByText('공지')).toBeInTheDocument();
    expect(within(first).getByRole('link', { name: new RegExp(NOTICE_TITLE) })).toHaveAttribute('href', '/board/notice/101');
    expect(within(first).getByText('2026.09.01')).toBeInTheDocument();
    expect(document.title).toBe('공지사항 | 조리읍주민자치센터');
  });

  it('상단공지가 아닌 게시물은 구분 칸에 번호 대신 비워 두지 않고 일반으로 보인다', async () => {
    server.use(
      http.get('/api/v1/boards/notice/posts', () =>
        HttpResponse.json(page([{ ...post('1', 'notice', '일반 공지'), pinned: false }])),
      ),
    );
    renderApp('/board/notice');
    const row = within(await screen.findByRole('table', { name: '공지사항 목록' })).getAllByRole('row')[1]!;
    expect(within(row).getByText('일반')).toBeInTheDocument();
  });

  it('제목으로 검색하면 주소에 검색어를 남기고 결과만 보인다', async () => {
    const { router } = renderApp('/board/notice');
    const u = user();
    await u.type(await screen.findByLabelText('제목으로 검색'), '통기타');
    await u.click(screen.getByRole('button', { name: '검색' }));

    await waitFor(() => expect(router.state.location.search).toBe('?q=%ED%86%B5%EA%B8%B0%ED%83%80'));
    const table = await screen.findByRole('table', { name: '공지사항 목록' });
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
    expect(within(table).getByText(/통기타 강사 모집 공고/)).toBeInTheDocument();
  });

  it('검색 결과가 없으면 안내하고 표를 보이지 않는다', async () => {
    renderApp('/board/notice?q=없는검색어');
    expect(await screen.findByText('검색 결과가 없습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('게시물이 한 쪽을 넘으면 쪽 이동을 보인다', async () => {
    server.use(
      http.get('/api/v1/boards/notice/posts', () =>
        HttpResponse.json({ ...page([post('1', 'notice', '첫 글')]), total: 25 }),
      ),
    );
    renderApp('/board/notice');
    const pager = await screen.findByRole('navigation', { name: '쪽 이동' });
    expect(within(pager).getByRole('link', { name: '2 쪽' })).toHaveAttribute('href', '/board/notice?page=2');
  });
  it('검색 중에 쪽을 옮겨도 검색어를 유지한다', async () => {
    server.use(
      http.get('/api/v1/boards/notice/posts', () =>
        HttpResponse.json({ ...page([post('1', 'notice', 'abc 공지')]), total: 25 }),
      ),
    );
    renderApp('/board/notice?q=abc');
    const pager = await screen.findByRole('navigation', { name: '쪽 이동' });
    expect(within(pager).getByRole('link', { name: '2 쪽' })).toHaveAttribute('href', '/board/notice?q=abc&page=2');
  });
});

describe('기관소식', () => {
  it('제목과 날짜를 한 줄씩 목록으로 보인다', async () => {
    renderApp('/board/news');

    expect(await screen.findByRole('heading', { level: 1, name: '기관소식' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 2, name: '센터 소식' })).toBeInTheDocument();
    const link = await screen.findByRole('link', { name: /조리읍 행정복지센터 신청사 개청/ });
    expect(link).toHaveAttribute('href', '/board/news/201');
    expect(within(link).getByText('2022.10.05')).toBeInTheDocument();
  });
});

describe('자료실', () => {
  it('제목(상세)과 자료 보기(첨부)를 구분해 보인다', async () => {
    renderApp('/board/resources');

    const table = await screen.findByRole('table', { name: '자료실 목록' });
    expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['제목', '등록일', '자료']);
    const first = within(table).getAllByRole('row')[1]!;
    expect(within(first).getByRole('link', { name: /2026년 4분기 교육프로그램 수강생 모집 안내/ })).toHaveAttribute('href', '/board/resources/301');
    const view = within(first).getByRole('link', { name: /자료 보기/ });
    expect(view).toHaveAttribute('href', expect.stringMatching(/^\/api\/v1\/files\/[0-9]+$/));
    expect(view).toHaveAttribute('target', '_blank');
    expect(view).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('첨부가 없는 게시물은 자료 보기를 보이지 않고 줄 표시를 남긴다', async () => {
    server.use(http.get('/api/v1/boards/resources/posts', () => HttpResponse.json(page([post('5', 'resources', '자료 없음')]))));
    renderApp('/board/resources');
    const row = within(await screen.findByRole('table', { name: '자료실 목록' })).getAllByRole('row')[1]!;
    expect(within(row).queryByRole('link', { name: /자료 보기/ })).not.toBeInTheDocument();
    expect(within(row).getByText('-')).toBeInTheDocument();
  });
});

describe('센터 갤러리', () => {
  it('대표 이미지와 제목, 날짜를 카드로 보이고 이미지는 서버 파일을 쓴다', async () => {
    renderApp('/board/gallery');

    expect(await screen.findByRole('heading', { level: 1, name: '센터 갤러리' })).toBeInTheDocument();
    const image = await screen.findByRole('img', { name: '조리읍 행정복지센터 신청사' });
    expect(image).toHaveAttribute('src', expect.stringMatching(/^\/api\/v1\/files\/[0-9]+$/));
    // 이미지와 제목이 같은 상세로 가는 링크 둘이다(시안과 같다).
    for (const link of screen.getAllByRole('link', { name: '조리읍 행정복지센터 신청사' })) {
      expect(link).toHaveAttribute('href', '/board/gallery/401');
    }
    expect(screen.getByRole('heading', { level: 2, name: '조리읍 행정복지센터 신청사' })).toBeInTheDocument();
    expect(screen.getByText('2022.10.05')).toBeInTheDocument();
  });
});

describe('자주하는 질문', () => {
  it('질문을 펼침 항목으로 보이고 첫 항목만 펼쳐 둔다', async () => {
    renderApp('/board/faq');

    expect(await screen.findByRole('heading', { level: 1, name: '자주하는 질문' })).toBeInTheDocument();
    const items = (await screen.findAllByText(/./, { selector: 'summary' })).map((node) => node.closest('details')!);
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveAttribute('open');
    expect(items[1]).not.toHaveAttribute('open');
    expect(within(items[0]!).getByText(/9월 7일부터 11일까지/)).toBeInTheDocument();
  });
});

describe('게시물 상세', () => {
  it('공고의 핵심 항목, 본문, 첨부파일, 목록으로 링크를 그린다', async () => {
    renderApp('/board/notice/101');

    expect(await screen.findByRole('heading', { level: 2, name: NOTICE_TITLE })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: '공지사항' })).toBeInTheDocument();
    expect(screen.getByText('등록일 2026.09.01')).toBeInTheDocument();
    const fact = (label: string) => screen.getByText(label, { selector: 'dt' }).nextElementSibling as HTMLElement;
    expect(fact('접수기간')).toHaveTextContent('2026.09.07 – 09.11');
    expect(within(fact('수강 문의')).getByRole('link')).toHaveAttribute('href', 'tel:031-941-7742');
    expect(screen.getByText(/방문 접수 후 계좌이체로 납부합니다/)).toBeInTheDocument();
    const files = screen.getByRole('list', { name: '첨부파일' });
    const link = within(files).getByRole('link', { name: /수강생 모집 안내 PDF/ });
    expect(link).toHaveAttribute('href', expect.stringMatching(/^\/api\/v1\/files\/[0-9]+$/));
    expect(link).toHaveAttribute('download');
    expect(screen.getByRole('link', { name: '목록으로' })).toHaveAttribute('href', '/board/notice');
    expect(crumbs().getByText(NOTICE_TITLE)).toBeInTheDocument();
    expect(document.title).toBe(`${NOTICE_TITLE} | 조리읍주민자치센터`);
  });

  it('갤러리 상세는 이미지를 크게 보인다', async () => {
    renderApp('/board/gallery/401');
    expect(await screen.findByRole('heading', { level: 2, name: '조리읍 행정복지센터 신청사' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: '조리읍 행정복지센터 신청사' })).toHaveAttribute('src', expect.stringMatching(/^\/api\/v1\/files\//));
    expect(screen.getByRole('link', { name: '목록으로' })).toHaveAttribute('href', '/board/gallery');
  });

  it('없는 번호나 다른 게시판의 번호는 찾을 수 없음이다', async () => {
    renderApp('/board/notice/999');
    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });

  it('공지 번호를 기관소식 주소로 열면 찾을 수 없음이다', async () => {
    renderApp('/board/news/101');
    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });

  it('홈의 공지 링크가 상세로 이어진다', async () => {
    const { router } = renderApp('/');
    const links = await screen.findAllByRole('link', { name: new RegExp(NOTICE_TITLE) });
    await user().click(links[0]!);
    await waitFor(() => expect(router.state.location.pathname).toBe('/board/notice/101'));
    expect(await screen.findByRole('heading', { level: 2, name: NOTICE_TITLE })).toBeInTheDocument();
  });
});

function post(id: string, board: string, title: string) {
  return {
    postId: id,
    board,
    title,
    publishedAt: '2026-09-01T09:00:00+09:00',
    pinned: true,
    body: null,
    primaryFile: null,
    thumbnail: null,
  };
}

function page(items: unknown[]) {
  return { items, page: 1, size: 10, total: items.length, criteria: { basisAt: '2026-09-01T09:00:00+09:00', description: null } };
}
