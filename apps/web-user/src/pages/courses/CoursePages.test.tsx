// 강좌 상세, 강의계획서, 분야별 강좌 화면이 서버 응답을 그대로 그리고 접수 상태에 따라 버튼이 달라지는지 확인하는 시험
import { screen, within } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { setMockNow } from '../../mocks/clock';
import { COURSE_SEEDS } from '../../mocks/courseData';
import { buildCoursePlan, findCourseSeed } from '../../mocks/fixtures';
import { renderApp, server, useMockServer } from '../../test/render';

useMockServer();

const AFTER = new Date('2026-11-01T10:00:00+09:00');
const DURING = new Date('2026-09-08T10:00:00+09:00');
const BEFORE = new Date('2026-08-20T10:00:00+09:00');

beforeEach(() => setMockNow(AFTER));
afterEach(() => setMockNow(null));

const idOf = (name: string) => COURSE_SEEDS.find((seed) => seed.name === name)!.id;
// 본문 칸(details-grid)만 본다. 오른쪽 수강 정보에도 '정원'이 있어 범위를 좁힌다.
const detail = (term: string) =>
  screen.findByText(term, { selector: '.details-grid dt' }).then((dt) => dt.nextElementSibling as HTMLElement);

describe('강좌 상세', () => {
  it('기간·일정·정원·강사·강의실을 시안의 칸대로 보인다', async () => {
    const seed = COURSE_SEEDS.find((s) => s.name === '요가A(중급)')!;
    renderApp(`/courses/${seed.id}`);

    expect(await screen.findByRole('heading', { level: 1, name: '요가A(중급)' })).toBeInTheDocument();
    expect(await detail('교육기간')).toHaveTextContent('2026.10.01 — 2026.12.31');
    expect(await detail('접수기간')).toHaveTextContent('2026.09.07 — 2026.09.11');
    expect(await detail('요일 · 시간')).toHaveTextContent('화·목 09:50~10:50');
    expect(await detail('정원')).toHaveTextContent('20명');
    expect(await detail('담당 강사')).toHaveTextContent('한은경');
    expect(await detail('강의실')).toHaveTextContent(seed.room!);
    expect(document.title).toBe('요가A(중급) | 조리읍주민자치센터');
  });

  it('접수마감이면 수강신청 링크 대신 꺼진 접수마감 버튼을 보이고 잔여석을 숨긴다', async () => {
    renderApp(`/courses/${idOf('요가A(중급)')}`);
    const booking = (await screen.findByRole('complementary', { name: '수강 정보' })) as HTMLElement;

    expect(within(booking).getByText('접수상태').nextElementSibling).toHaveTextContent('접수마감');
    expect(within(booking).getByRole('button', { name: '접수마감' })).toBeDisabled();
    expect(within(booking).queryByRole('link', { name: '수강신청' })).not.toBeInTheDocument();
    expect(within(booking).getByText('정원').nextElementSibling).toHaveTextContent(/^20명$/);
    expect(within(booking).getByText('60,000원')).toBeInTheDocument();
    expect(within(booking).getByText('2026년 4분기 · 생활체육/건강')).toBeInTheDocument();
  });

  it('접수중이면 수강신청 링크와 잔여석을 보인다', async () => {
    setMockNow(DURING);
    const id = idOf('요가A(중급)');
    renderApp(`/courses/${id}`);
    const booking = (await screen.findByRole('complementary', { name: '수강 정보' })) as HTMLElement;

    expect(within(booking).getByRole('link', { name: '수강신청' })).toHaveAttribute('href', `/apply/${id}`);
    expect(within(booking).queryByRole('button')).not.toBeInTheDocument();
    // 정원 20명의 60%(12명)가 찬 시험용 값이라 8석이 남는다.
    expect(within(booking).getByText('정원').nextElementSibling).toHaveTextContent('20명 (잔여 8석)');
  });

  it('접수예정이면 꺼진 접수예정 버튼을 보인다', async () => {
    setMockNow(BEFORE);
    renderApp(`/courses/${idOf('요가A(중급)')}`);
    const booking = (await screen.findByRole('complementary', { name: '수강 정보' })) as HTMLElement;

    expect(within(booking).getByRole('button', { name: '접수예정' })).toBeDisabled();
    expect(within(booking).queryByRole('link', { name: '수강신청' })).not.toBeInTheDocument();
  });

  it('강사가 없으면 시안 문구를, 요일마다 시간이 다르면 풀어 쓴 표기를 보인다', async () => {
    renderApp(`/courses/${idOf('헬스')}`);
    expect(await detail('담당 강사')).toHaveTextContent('시간표 미기재');
    expect(await detail('요일 · 시간')).toHaveTextContent('월~금 10:00~21:00');
    expect(await detail('정원')).toHaveTextContent('180명');
  });

  it('요일마다 시간이 다른 강좌는 요일별 시간을 모두 보인다', async () => {
    renderApp(`/courses/${idOf('한국무용')}`);
    expect(await detail('요일 · 시간')).toHaveTextContent('수·금 (수)12:00~13:30 / (금)10:00~11:30');
  });

  it('강의 안내와 강의계획서 링크, 신청·결제 안내, 되돌아가는 링크가 있다', async () => {
    const id = idOf('요가A(중급)');
    renderApp(`/courses/${id}`);

    expect(await screen.findByRole('link', { name: '강의계획서 보기 →' })).toHaveAttribute('href', `/courses/${id}/plan`);
    expect(screen.getByText(/공식 시간표 기준입니다/)).toBeInTheDocument();
    expect(screen.getByText('유료 자리 배정 후 10분(600초) 안에 결제합니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '강좌 목록' })).toHaveAttribute('href', '/courses');
    expect(screen.getByRole('link', { name: '환불·휴강 안내' })).toHaveAttribute('href', '/guide/refund');
    // 시안 검토용 안내는 서비스 화면에 가져오지 않는다.
    expect(screen.queryByText(/신규 웹서비스 시안/)).not.toBeInTheDocument();
    expect(screen.queryByText('화면 상태 선택')).not.toBeInTheDocument();
  });

  it('현재 위치에 강좌정보와 강좌 이름을 보이고 본문 영역에 상세형 클래스를 준다', async () => {
    renderApp(`/courses/${idOf('요가A(중급)')}`);
    const crumbs = await screen.findByRole('navigation', { name: '현재 위치' });
    expect(within(crumbs).getByRole('link', { name: '강좌정보' })).toHaveAttribute('href', '/courses');
    expect(within(crumbs).getByText('요가A(중급)').tagName).toBe('STRONG');
    expect(document.getElementById('main')).toHaveClass('service-page');
  });

  it('없는 강좌는 찾을 수 없다는 화면을 보인다', async () => {
    renderApp('/courses/9999');
    expect(await screen.findByRole('heading', { level: 1, name: '페이지를 찾을 수 없습니다' })).toBeInTheDocument();
  });

  it('숫자가 아닌 강좌 번호도 오류 화면을 거치지 않고 찾을 수 없음으로 처리한다', async () => {
    renderApp('/courses/abc');
    expect(await screen.findByRole('heading', { level: 1, name: '페이지를 찾을 수 없습니다' })).toBeInTheDocument();
  });

  it('서버 오류면 불러오지 못했다는 안내와 다시 시도 버튼을 보인다', async () => {
    server.use(
      http.get('/api/v1/courses/:courseId', () =>
        HttpResponse.json({ code: 'INTERNAL_ERROR', message: '오류', requestId: 'req-test-0002' }, { status: 500 }),
      ),
    );
    renderApp('/courses/1');
    expect(await screen.findByRole('alert')).toHaveTextContent('강좌 정보를 불러오지 못했습니다');
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeInTheDocument();
  });
});

describe('강의계획서', () => {
  it('아직 등록되지 않았으면 추후 등록된다고 안내하고 강좌 정보를 함께 보인다', async () => {
    const id = idOf('요가A(중급)');
    renderApp(`/courses/${id}/plan`);

    expect(await screen.findByRole('heading', { level: 1, name: '강의계획서' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: '요가A(중급)' })).toBeInTheDocument();
    expect(await detail('담당 강사')).toHaveTextContent('한은경');
    expect(await detail('정원')).toHaveTextContent('20명');
    expect(screen.getByText('강의계획서는 추후 등록될 예정입니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '강좌 상세' })).toHaveAttribute('href', `/courses/${id}`);
    expect(document.title).toBe('강의계획서 | 조리읍주민자치센터');
  });

  it('현재 위치에 강좌 이름이 링크로 들어간다', async () => {
    const id = idOf('요가A(중급)');
    renderApp(`/courses/${id}/plan`);
    const crumbs = await screen.findByRole('navigation', { name: '현재 위치' });
    expect(await within(crumbs).findByRole('link', { name: '요가A(중급)' })).toHaveAttribute('href', `/courses/${id}`);
  });

  it('계획 본문이 등록되어 있으면 본문을 보이고 등록 안내는 감춘다', async () => {
    const seed = findCourseSeed(idOf('요가A(중급)'))!;
    server.use(
      http.get('/api/v1/courses/:courseId/plan', () =>
        HttpResponse.json({ ...buildCoursePlan(seed), planText: '1회차 호흡과 기초 자세\n2회차 균형 잡기' }),
      ),
    );
    renderApp(`/courses/${seed.id}/plan`);

    expect(await screen.findByText(/1회차 호흡과 기초 자세/)).toBeInTheDocument();
    expect(screen.queryByText('강의계획서는 추후 등록될 예정입니다.')).not.toBeInTheDocument();
  });

  it('첨부 파일이 있으면 이름과 크기로 내려받는 링크를 보인다', async () => {
    const seed = findCourseSeed(idOf('요가A(중급)'))!;
    server.use(
      http.get('/api/v1/courses/:courseId/plan', () =>
        HttpResponse.json({
          ...buildCoursePlan(seed),
          planFile: { fileId: '778899', name: '요가A 강의계획서.pdf', sizeBytes: 2 * 1024 * 1024 },
        }),
      ),
    );
    renderApp(`/courses/${seed.id}/plan`);

    const link = await screen.findByRole('link', { name: '요가A 강의계획서.pdf (2.0MB)' });
    expect(link).toHaveAttribute('href', '/api/v1/files/778899');
    expect(link).toHaveAttribute('download');
  });

  it('없는 강좌의 강의계획서는 찾을 수 없음이다', async () => {
    renderApp('/courses/9999/plan');
    expect(await screen.findByRole('heading', { level: 1, name: '페이지를 찾을 수 없습니다' })).toBeInTheDocument();
  });
});

describe('분야별 강좌', () => {
  it('분야의 강좌 수와 강좌·강사를 쪽 나눔 없이 모두 보인다', async () => {
    renderApp('/courses/field/3');

    expect(await screen.findByRole('heading', { level: 1, name: '생활체육/건강 강좌' })).toBeInTheDocument();
    expect(await screen.findByText('강좌 9개')).toBeInTheDocument();
    expect(screen.getByText('2026년 4분기')).toBeInTheDocument();
    const links = within(document.querySelector('.course-category-list') as HTMLElement).getAllByRole('link');
    expect(links).toHaveLength(9);
    expect(links[0]).toHaveTextContent('라인댄스 A정은경');
    expect(links[0]).toHaveAttribute('href', '/courses/3');
    expect(screen.queryByRole('navigation', { name: '쪽 이동' })).not.toBeInTheDocument();
  });

  it('강사가 없는 강좌는 시안 문구를 보인다', async () => {
    renderApp('/courses/field/3');
    expect(await screen.findByRole('link', { name: /헬스/ })).toHaveTextContent('헬스시간표 미기재');
  });

  it('50개 이하인 분야는 한 번에 가져온다 (문화/취미 12개)', async () => {
    renderApp('/courses/field/4');
    expect(await screen.findByText('강좌 12개')).toBeInTheDocument();
    expect(document.querySelectorAll('.course-category-list a')).toHaveLength(12);
  });

  it('전체 강좌로 돌아가는 버튼과 현재 위치를 보인다', async () => {
    renderApp('/courses/field/1');
    // 머리글 드롭다운에도 '전체 강좌' 링크가 있어 화면 제목이 뜬 뒤에 확인한다.
    await screen.findByRole('heading', { level: 1, name: '컴퓨터 강좌' });
    expect(within(document.getElementById('main')!).getByRole('link', { name: '전체 강좌' })).toHaveAttribute('href', '/courses');
    const crumbs = screen.getByRole('navigation', { name: '현재 위치' });
    expect(within(crumbs).getByText('컴퓨터 강좌').tagName).toBe('STRONG');
  });

  it('없는 분야는 찾을 수 없음이다', async () => {
    renderApp('/courses/field/99');
    expect(await screen.findByRole('heading', { level: 1, name: '페이지를 찾을 수 없습니다' })).toBeInTheDocument();
  });

  it('홈의 분야 카드가 이 화면으로 연결된다', async () => {
    renderApp('/');
    const card = await screen.findByRole('link', { name: /문화\/취미/ });
    expect(card).toHaveAttribute('href', '/courses/field/4');
  });
});
