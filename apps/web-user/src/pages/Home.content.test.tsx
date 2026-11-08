// 홈의 비주얼·배너·팝업(서버가 내려준 값만 그림, 이미지 대체 문구, 링크 종류, 오늘 하루 보지 않기, 비었을 때 기본 화면)을 확인하는 시험
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, describe, expect, it } from 'vitest';
import { setMockNow } from '../mocks/clock';
import { setMockHomeContent } from '../mocks/homeContent';
import { renderApp, server, useMockServer } from '../test/render';

useMockServer();

afterEach(() => {
  setMockHomeContent(null);
  setMockNow(null);
  window.localStorage.clear();
});

const popup = () => screen.findByRole('dialog', { name: '휴관일 안내' });

describe('홈 비주얼', () => {
  it('서버가 비주얼을 내려주면 그 문구와 사진과 링크를 그린다', async () => {
    setMockHomeContent('full');
    renderApp('/');
    const title = await screen.findByText('함께 배우고, 함께 자라는 조리읍.');
    const section = title.closest('section')!;
    expect(within(section).getByRole('img', { name: '조리읍 행정복지센터 청사' })).toHaveAttribute('src', '/api/v1/files/9100000000000000000501');
    expect(within(section).getByRole('link', { name: /자세히 보기/ })).toHaveAttribute('href', '/courses');
    expect(within(section).getByText('시험용 문구: 함께 배우는 즐거움')).toBeInTheDocument();
    expect(within(section).queryByText(/파주시 제공/)).not.toBeInTheDocument();
  });

  it('비주얼이 없으면 기본 문구와 강좌 둘러보기를 그린다', async () => {
    renderApp('/');
    const hero = await screen.findByRole('heading', { level: 1 });
    expect(within(hero).getByText(/함께 배우고,/)).toBeInTheDocument();
    expect(within(hero.closest('section')!).getByRole('link', { name: /강좌 둘러보기/ })).toHaveAttribute('href', '/courses');
  });
});

describe('홈 배너', () => {
  it('이미지가 있는 배너는 사진과 제목을, 없는 배너는 제목만 그리고 링크 종류에 맞게 연다', async () => {
    setMockHomeContent('full');
    renderApp('/');
    const region = await screen.findByRole('region', { name: '안내 배너' });
    const first = within(region).getByRole('link', { name: /수강신청 접수 안내/ });
    expect(first).toHaveAttribute('href', '/guide/apply');
    expect(within(first).getByRole('img', { name: '수강신청 접수 안내 배너' })).toBeInTheDocument();
    const second = within(region).getByRole('link', { name: /접수 예정 안내/ });
    expect(second).toHaveAttribute('href', 'https://www.paju.go.kr');
    expect(second).toHaveAttribute('target', '_blank');
    expect(second).toHaveAttribute('rel', 'noopener noreferrer');
    expect(within(second).getByText('(새 창)')).toBeInTheDocument();
    expect(within(second).queryByRole('img')).not.toBeInTheDocument();
  });

  it('배너가 없으면 영역 자체가 없다', async () => {
    renderApp('/');
    await screen.findByRole('heading', { name: '센터 소식' }); // 홈 응답을 받은 뒤에 확인한다
    expect(screen.queryByRole('region', { name: '안내 배너' })).not.toBeInTheDocument();
  });

  it('사이트 밖으로 새는 주소나 알 수 없는 형식은 링크로 만들지 않는다', async () => {
    server.use(
      http.get('/api/v1/home', () =>
        HttpResponse.json({
          serverNow: '2026-09-08T10:00:00+09:00', cycle: null, categories: [], notices: [], visual: null, popups: [],
          banners: [
            { contentId: '1', title: '위험한 주소', linkUrl: '//evil.example.com', image: null },
            { contentId: '2', title: '스크립트 주소', linkUrl: 'javascript:alert(1)', image: null },
            { contentId: '3', title: '주소 없음', linkUrl: null, image: null },
            { contentId: '4', title: '보호되지 않은 주소', linkUrl: 'http://insecure.example.com', image: null },
          ],
        }),
      ),
    );
    renderApp('/');
    const region = await screen.findByRole('region', { name: '안내 배너' });
    expect(within(region).queryAllByRole('link')).toHaveLength(0);
    expect(within(region).getByText('위험한 주소')).toBeInTheDocument();
    expect(within(region).getByText('스크립트 주소')).toBeInTheDocument();
    expect(within(region).getByText('보호되지 않은 주소')).toBeInTheDocument();
  });
});

describe('홈 팝업', () => {
  it('게시기간 안의 팝업을 안내 창으로 보이고 닫으면 사라진다', async () => {
    setMockHomeContent('full');
    renderApp('/');
    const dialog = await popup();
    expect(dialog).toHaveAttribute('aria-modal', 'false');
    expect(within(dialog).getByText('11월 1일부터 10일까지 휴관합니다.')).toBeInTheDocument();
    expect(within(dialog).getByRole('img', { name: '휴관일 안내 이미지' })).toBeInTheDocument();
    expect(within(dialog).getByRole('link', { name: '자세히 보기' })).toHaveAttribute('href', '/center/contact');
    await userEvent.click(within(dialog).getByRole('button', { name: '닫기' }));
    expect(screen.queryByRole('dialog', { name: '휴관일 안내' })).not.toBeInTheDocument();
  });

  it('닫기만 누르면 다시 열었을 때 또 보이고 오늘 하루 보지 않기를 누르면 같은 날에는 보이지 않는다', async () => {
    setMockHomeContent('full');
    setMockNow(new Date('2026-09-08T10:00:00+09:00'));
    const first = renderApp('/');
    await userEvent.click(within(await popup()).getByRole('button', { name: '닫기' }));
    first.unmount();

    const second = renderApp('/');
    await userEvent.click(within(await popup()).getByRole('button', { name: '오늘 하루 보지 않기' }));
    expect(screen.queryByRole('dialog', { name: '휴관일 안내' })).not.toBeInTheDocument();
    expect(window.localStorage.getItem('popup-hidden:2000000000000000000005')).toBe('2026-09-08');
    second.unmount();

    setMockNow(new Date('2026-09-08T20:00:00+09:00')); // 같은 날 저녁
    renderApp('/');
    await screen.findByRole('region', { name: '안내 배너' }); // 홈 응답을 받은 뒤에 확인한다
    expect(screen.queryByRole('dialog', { name: '휴관일 안내' })).not.toBeInTheDocument();
  });

  it('다음 날에는 오늘 하루 보지 않기가 풀려 다시 보인다', async () => {
    setMockHomeContent('full');
    window.localStorage.setItem('popup-hidden:2000000000000000000005', '2026-09-08');
    setMockNow(new Date('2026-09-09T10:00:00+09:00'));
    renderApp('/');
    expect(await popup()).toBeInTheDocument();
  });

  it('게시기간이 지나 서버가 내려주지 않으면 팝업이 없다', async () => {
    setMockHomeContent('full');
    setMockNow(new Date('2027-02-01T10:00:00+09:00'));
    renderApp('/');
    await screen.findByRole('region', { name: '안내 배너' }); // 홈 응답을 받은 뒤에 확인한다
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('저장소를 쓸 수 없어도 팝업은 보이고 닫을 수 있다', async () => {
    setMockHomeContent('full');
    const original = Storage.prototype.getItem;
    Storage.prototype.getItem = () => {
      throw new Error('저장소 사용 불가');
    };
    try {
      renderApp('/');
      await userEvent.click(within(await popup()).getByRole('button', { name: '오늘 하루 보지 않기' }));
      expect(screen.queryByRole('dialog', { name: '휴관일 안내' })).not.toBeInTheDocument();
    } finally {
      Storage.prototype.getItem = original;
    }
  });
});