// 홈 화면이 API 응답을 그대로 그리는지, 비어 있거나 실패했을 때 지어내지 않는지 확인하는 시험
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';
import { buildHome, contact } from '../mocks/fixtures';
import { renderApp, server, useMockServer } from '../test/render';

useMockServer();

const AFTER_RECEPTION = new Date('2026-11-01T10:00:00+09:00');
const DURING_RECEPTION = new Date('2026-09-08T10:00:00+09:00');
const BEFORE_RECEPTION = new Date('2026-08-20T10:00:00+09:00');

function serveHome(now: Date) {
  server.use(http.get('/api/v1/home', () => HttpResponse.json(buildHome(now))));
}

describe('홈 화면', () => {
  it('분야 카드와 접수·교육 기간을 서버 응답대로 그린다', async () => {
    serveHome(AFTER_RECEPTION);
    renderApp('/');

    const grid = await screen.findByLabelText('분야별 강좌안내');
    const cards = within(grid).getAllByRole('link');
    expect(cards).toHaveLength(4);
    expect(within(cards[0]!).getByRole('heading', { name: '컴퓨터' })).toBeInTheDocument();
    expect(within(cards[0]!).getByText('초급컴퓨터 · 파워디렉터(영상편집)')).toBeInTheDocument();
    expect(within(cards[2]!).getByText('라인댄스 A · 요가A(중급) · 라인댄스 B')).toBeInTheDocument();
    expect(within(cards[0]!).getByText('2026.09.07 — 09.11')).toBeInTheDocument();
    expect(within(cards[0]!).getByText('2026.10.01 — 12.31')).toBeInTheDocument();
    expect(cards[0]).toHaveAttribute('href', '/courses/field/1');
  });

  it.each([
    [AFTER_RECEPTION, '접수마감'],
    [DURING_RECEPTION, '접수중'],
    [BEFORE_RECEPTION, '접수예정'],
  ])('접수 상태 문구는 서버가 준 상태를 그대로 옮긴다 (%s → %s)', async (now, label) => {
    serveHome(now);
    renderApp('/');

    const grid = await screen.findByLabelText('분야별 강좌안내');
    const badges = within(grid).getAllByText(label);
    expect(badges).toHaveLength(4);
  });

  it('화면은 날짜를 비교해 상태를 바꾸지 않는다', async () => {
    // 날짜상으로는 접수 기간 밖이지만 서버가 OPEN이라고 하면 그대로 따른다.
    const home = buildHome(AFTER_RECEPTION);
    server.use(
      http.get('/api/v1/home', () =>
        HttpResponse.json({
          ...home,
          categories: home.categories.map((item) => ({ ...item, receptionState: 'OPEN' })),
        }),
      ),
    );
    renderApp('/');

    const grid = await screen.findByLabelText('분야별 강좌안내');
    expect(within(grid).getAllByText('접수중')).toHaveLength(4);
    expect(within(grid).queryByText('접수마감')).not.toBeInTheDocument();
  });

  it('센터 소식은 공지 링크와 날짜를 그린다', async () => {
    serveHome(AFTER_RECEPTION);
    renderApp('/');

    const link = await screen.findByRole('link', { name: /2026년 4분기 조리읍주민자치센터 수강생 모집/ });
    expect(link).toHaveAttribute('href', '/board/notice/101');
    expect(within(link).getByText('2026.09.01')).toBeInTheDocument();
  });

  it('교육기수가 있으면 배너와 쉬운 화면 안내에 기수 이름과 기간을 쓴다', async () => {
    serveHome(AFTER_RECEPTION);
    renderApp('/');

    const banner = (await screen.findByText('교육프로그램 안내')).closest('.program-banner') as HTMLElement;
    expect(within(banner).getByText('2026년 4분기')).toBeInTheDocument();
    expect(within(banner).getByText('10.01 — 12.31')).toBeInTheDocument();
    expect(within(banner).getByText('접수마감 · 강좌별 상세 일정 확인')).toBeInTheDocument();

    expect(
      screen.getByText('접수가 마감되었습니다. 교육기간은 10월 1일 ~ 12월 31일입니다.'),
    ).toBeInTheDocument();
  });

  it('교육기수가 없으면 배너와 쉬운 화면 기수 안내를 숨긴다', async () => {
    server.use(http.get('/api/v1/home', () => HttpResponse.json({ ...buildHome(AFTER_RECEPTION), cycle: null })));
    renderApp('/');

    await screen.findByLabelText('분야별 강좌안내');
    expect(screen.queryByText('교육프로그램 안내')).not.toBeInTheDocument();
    expect(screen.queryByText(/교육기간은/)).not.toBeInTheDocument();
  });

  it('연락처가 비어 있으면 번호를 지어내지 않고 확인 필요로 표시한다', async () => {
    serveHome(AFTER_RECEPTION);
    server.use(
      http.get('/api/v1/site/contact', () =>
        HttpResponse.json({ ...contact, phone: null, adminOfficePhone: null, postalCode: null, address: null, floorInfo: null }),
      ),
    );
    renderApp('/');

    await screen.findByLabelText('분야별 강좌안내');
    expect(screen.getAllByText(/확인 필요/).length).toBeGreaterThan(0);
    expect(document.querySelector('a[href^="tel:"]')).toBeNull();
    expect(screen.queryByText(/031-/)).not.toBeInTheDocument();
  });

  it('불러오기에 실패하면 안내와 다시 시도 버튼을 보이고 누르면 다시 불러온다', async () => {
    let calls = 0;
    server.use(
      http.get('/api/v1/home', () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json(
            { code: 'INTERNAL_ERROR', message: '일시적인 오류', requestId: 'req-test-0001' },
            { status: 500 },
          );
        }
        return HttpResponse.json(buildHome(AFTER_RECEPTION));
      }),
    );
    renderApp('/');

    expect(await screen.findByRole('alert')).toHaveTextContent('불러오지 못했습니다');
    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByLabelText('분야별 강좌안내')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it('기본 화면과 쉬운 화면의 문구를 모두 문서에 두고 CSS가 보이는 쪽을 정한다', async () => {
    serveHome(AFTER_RECEPTION);
    renderApp('/');

    await screen.findByLabelText('분야별 강좌안내');
    const hero = document.querySelector('.hero') as HTMLElement;
    expect(within(hero).getByText(/함께 자라는 조리읍/)).toHaveClass('standard-only');
    expect(within(hero).getByText('무엇을 도와드릴까요?')).toHaveClass('easy-only');
  });
});
