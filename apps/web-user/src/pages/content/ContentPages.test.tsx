// 안내·센터소개 화면(수강 및 결제 안내, 환불 안내, 연혁, 시설안내, 위치 및 연락처)이 서버 문서를 그대로 그리는지 확인하는 시험
import { screen, within } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp, server, useMockServer } from '../../test/render';

useMockServer();

const crumbs = () => within(screen.getByRole('navigation', { name: '현재 위치' }));

describe('수강 및 결제 안내', () => {
  it('히어로 제목, 현재 위치, 좌측 메뉴의 현재 항목과 서버 문서의 절을 그린다', async () => {
    renderApp('/guide/apply');

    expect(await screen.findByRole('heading', { level: 1, name: '수강 및 결제 안내' })).toBeInTheDocument();
    expect(crumbs().getByText('강좌정보')).toBeInTheDocument();
    expect(crumbs().getByText('수강 및 결제 안내').tagName).toBe('STRONG');
    const menu = screen.getByRole('navigation', { name: '강좌정보 하위 메뉴' });
    expect(within(menu).getByRole('link', { name: /수강 및 결제 안내/ })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('heading', { level: 2, name: '2026년 4분기 현행 접수 안내' })).toBeInTheDocument();
    expect(screen.getByText(/수강료는 계좌이체이며 현금·카드 납부는 불가합니다/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '공식 모집 안내·첨부자료 →' })).toHaveAttribute('href', '/board/notice');
    expect(document.title).toBe('수강 및 결제 안내 | 조리읍주민자치센터');
  });

  it('온라인 신청 안내는 번호 붙은 단계로 그린다', async () => {
    renderApp('/guide/apply');

    expect(await screen.findByRole('heading', { level: 2, name: '온라인 신청 안내' })).toBeInTheDocument();
    const steps = screen.getByRole('list', { name: '온라인 신청 안내 단계' });
    const items = within(steps).getAllByRole('listitem');
    expect(items).toHaveLength(4);
    expect(within(items[2]!).getByText('유료 자리 배정 후 10분 결제')).toBeInTheDocument();
    expect(steps.tagName).toBe('OL');
  });

  it('사이트 안 링크는 앱 안에서 이동하고 바깥 주소는 새 창 없이 그대로 연다', async () => {
    server.use(
      http.get('/api/v1/contents/guide-apply', () =>
        HttpResponse.json({
          slug: 'guide-apply',
          title: '수강 및 결제 안내',
          subtitle: null,
          updatedOn: null,
          sections: [
            {
              heading: '링크',
              paragraphs: [],
              steps: [],
              items: [],
              table: null,
              links: [
                { label: '내 신청', url: '/me/applications' },
                { label: '공식 사이트', url: 'https://www.paju.go.kr/' },
              ],
            },
          ],
        }),
      ),
    );
    renderApp('/guide/apply');

    expect(await screen.findByRole('link', { name: '내 신청' })).toHaveAttribute('href', '/me/applications');
    const external = screen.getByRole('link', { name: '공식 사이트' });
    expect(external).toHaveAttribute('href', 'https://www.paju.go.kr/');
    expect(external).toHaveAttribute('rel', 'noopener noreferrer');
  });
});

describe('환불 및 휴강일 안내', () => {
  it('공식 환불 안내와 환불 절차 단계, 휴강·보강 안내를 그린다', async () => {
    renderApp('/guide/refund');

    expect(await screen.findByRole('heading', { level: 1, name: '환불 및 휴강일 안내' })).toBeInTheDocument();
    expect(screen.getByText(/개강 전에는 수강료 전액을 환불하며/)).toBeInTheDocument();
    const steps = screen.getByRole('list', { name: '온라인 환불 신청 절차 단계' });
    expect(within(steps).getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByRole('heading', { level: 2, name: '휴강·보강 안내' })).toBeInTheDocument();
  });
});

describe('센터소개', () => {
  it('연혁은 연도별 항목으로 그리고 센터소개 메뉴의 현재 항목을 표시한다', async () => {
    renderApp('/center/history');

    expect(await screen.findByRole('heading', { level: 1, name: '연혁' })).toBeInTheDocument();
    expect(screen.getByText('공식 자료로 확인된 센터 이력입니다.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: '2022' })).toBeInTheDocument();
    expect(screen.getByText('조리읍 행정복지센터 신청사 개청')).toBeInTheDocument();
    expect(screen.getByText('10월 5일')).toBeInTheDocument();
    expect(screen.getByText('그 외 연혁은 확인 후 추가합니다.')).toBeInTheDocument();
    const menu = screen.getByRole('navigation', { name: '센터소개 하위 메뉴' });
    expect(within(menu).getByRole('link', { name: /연혁/ })).toHaveAttribute('aria-current', 'page');
    expect(crumbs().getByText('센터소개')).toBeInTheDocument();
  });

  it('시설안내는 층별 표와 찾아오시는 길 링크를 그린다', async () => {
    renderApp('/center/facility');

    expect(await screen.findByRole('heading', { level: 1, name: '시설안내' })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: '조리읍 행정복지센터 표' });
    expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['층', '시설']);
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(4);
    expect(within(rows[2]!).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['3층', '주민자치센터']);
    expect(screen.getByRole('link', { name: '찾아오시는 길 →' })).toHaveAttribute('href', '/center/contact');
  });

  it('위치 및 연락처는 연락처 응답의 주소와 전화번호를 그린다', async () => {
    renderApp('/center/contact');

    expect(await screen.findByRole('heading', { level: 1, name: '위치 및 연락처' })).toBeInTheDocument();
    const address = screen.getByText('주소', { selector: 'dt' }).nextElementSibling as HTMLElement;
    expect(address).toHaveTextContent('[10937] 경기도 파주시 조리읍 봉천로 64');
    const visit = screen.getByText('방문 위치', { selector: 'dt' }).nextElementSibling as HTMLElement;
    expect(visit).toHaveTextContent('3층');
    const inquiry = screen.getByText('수강 문의', { selector: 'dt' }).nextElementSibling as HTMLElement;
    expect(within(inquiry).getByRole('link')).toHaveAttribute('href', 'tel:031-941-7742');
    const office = screen.getByText('센터 대표', { selector: 'dt' }).nextElementSibling as HTMLElement;
    expect(within(office).getByRole('link')).toHaveAttribute('href', 'tel:031-940-8121');
    expect(screen.getByRole('link', { name: '층별 시설 안내' })).toHaveAttribute('href', '/center/facility');
  });

  it('연락처가 비어 있으면 확인 필요로 표시한다', async () => {
    server.use(http.get('/api/v1/site/contact', () => HttpResponse.json({})));
    renderApp('/center/contact');

    expect(await screen.findByRole('heading', { level: 1, name: '위치 및 연락처' })).toBeInTheDocument();
    const address = screen.getByText('주소', { selector: 'dt' }).nextElementSibling as HTMLElement;
    expect(address).toHaveTextContent('확인 필요');
  });
});

describe('문서를 불러오지 못할 때', () => {
  it('서버가 404를 주면 찾을 수 없음 화면을 보인다', async () => {
    server.use(
      http.get('/api/v1/contents/center-history', () =>
        HttpResponse.json({ code: 'NOT_FOUND', message: '없음', requestId: 'r' }, { status: 404 }),
      ),
    );
    renderApp('/center/history');
    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });

  it('서버 오류이면 다시 시도 버튼을 보인다', async () => {
    server.use(
      http.get('/api/v1/contents/center-facility', () =>
        HttpResponse.json({ code: 'INTERNAL_ERROR', message: '오류', requestId: 'r' }, { status: 500 }),
      ),
    );
    renderApp('/center/facility');
    expect(await screen.findByRole('button', { name: '다시 시도' })).toBeInTheDocument();
  });
});
