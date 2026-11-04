// 강사현황·강사 상세·모집공고·강사 지원서·내 지원내역이 서버 판정대로 그려지고 지원이 올바르게 전송되는지 확인하는 시험
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { setMockNow } from '../../mocks/clock';
import { renderApp, server, signInAsDemo, useMockServer } from '../../test/render';

useMockServer();

const DURING = new Date('2026-09-08T10:00:00+09:00'); // 모의 모집공고(요가)가 모집중인 때
beforeEach(() => setMockNow(DURING));
afterEach(() => setMockNow(null));

const user = () => userEvent.setup({ delay: null });
const crumbs = () => within(screen.getByRole('navigation', { name: '현재 위치' }));
const definition = (term: string) => screen.getByText(term, { selector: 'dt' }).nextElementSibling as HTMLElement;
const OPEN_ID = '2';

async function fillApplication(u: ReturnType<typeof user>, course = '요가 심화반') {
  await u.type(await screen.findByLabelText('희망 강좌명'), course);
  await u.type(screen.getByLabelText('경력 및 강의소개'), '요가 강사 경력 5년');
  await u.click(screen.getByRole('checkbox', { name: '제출 내용을 확인했습니다.' }));
}

describe('강사현황', () => {
  it('시간표에 수록된 강사를 표로 보이고 강사명·분야·담당 강좌·소개 링크를 둔다', async () => {
    renderApp('/instructors');

    expect(await screen.findByRole('heading', { level: 1, name: '강사현황' })).toBeInTheDocument();
    expect(crumbs().getByText('강사은행')).toBeInTheDocument();
    expect(await screen.findByText('2026년 4분기 시간표에 수록된 강사 18명')).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: '강사 목록' });
    expect(within(table).getAllByRole('columnheader').map((c) => c.textContent)).toEqual(['강사명', '분야', '담당 강좌', '소개']);
    const first = within(table).getAllByRole('row')[1]!;
    expect(within(first).getAllByRole('cell').map((c) => c.textContent)).toEqual(['추순자', '컴퓨터', '초급컴퓨터, 파워디렉터(영상편집)', '강사 소개']);
    expect(within(first).getByRole('link', { name: '강사 소개 (추순자)' })).toHaveAttribute('href', '/instructors/1');
    expect(within(table).getAllByRole('row')).toHaveLength(11);
    expect(screen.getByRole('search', { name: '강사·강좌 검색' })).toBeInTheDocument();
    expect(document.title).toBe('강사현황 | 조리읍주민자치센터');
  });

  it('강사명이나 강좌명으로 검색하면 주소에 검색어를 남기고 맞는 강사만 보인다', async () => {
    const { router } = renderApp('/instructors');
    const u = user();
    await u.type(await screen.findByRole('searchbox', { name: '강사·강좌 검색' }), '라인댄스');
    await u.click(within(screen.getByRole('search', { name: '강사·강좌 검색' })).getByRole('button', { name: '검색' }));

    await waitFor(() => expect(router.state.location.search).toBe(`?q=${encodeURIComponent('라인댄스')}`));
    const table = await screen.findByRole('table', { name: '강사 목록' });
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
    // 강좌명 검색이라 그 강좌를 맡은 강사 한 명이 담당 강좌 셋과 함께 보인다.
    expect(within(within(table).getAllByRole('row')[1]!).getAllByRole('cell')[0]!).toHaveTextContent('정은경');
  });

  it('검색 결과가 없으면 안내한다', async () => {
    renderApp('/instructors?q=없는검색어');
    expect(await screen.findByText('검색 결과가 없습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('한 쪽을 넘으면 쪽 이동을 보이고 검색어를 유지한다', async () => {
    server.use(
      http.get('/api/v1/instructors', () =>
        HttpResponse.json({
          items: [{ instructorId: '1', name: '가강사', categoryName: '컴퓨터', courseNames: ['a'] }],
          page: 1,
          size: 10,
          total: 25,
          criteria: { basisAt: '2026-09-08T10:00:00+09:00', description: null },
        }),
      ),
    );
    renderApp('/instructors?q=a');
    const pager = await screen.findByRole('navigation', { name: '쪽 이동' });
    expect(within(pager).getByRole('link', { name: '2 쪽' })).toHaveAttribute('href', '/instructors?q=a&page=2');
  });
});

describe('강사 상세', () => {
  it('강의 분야·담당 강좌와 경력 없음 안내, 담당 강좌 찾기 링크를 그린다', async () => {
    renderApp('/instructors/1');

    expect(await screen.findByRole('heading', { level: 2, name: '추순자' })).toBeInTheDocument();
    expect(definition('강의 분야')).toHaveTextContent('컴퓨터');
    expect(definition('담당 강좌')).toHaveTextContent('초급컴퓨터, 파워디렉터(영상편집)');
    expect(screen.getByRole('heading', { level: 3, name: '경력 및 자격' })).toBeInTheDocument();
    expect(screen.getByText('공식 시간표에는 경력·자격 정보가 수록되어 있지 않습니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '담당 강좌 찾기' })).toHaveAttribute('href', `/courses?q=${encodeURIComponent('추순자')}`);
    expect(screen.getByRole('link', { name: '강사 목록' })).toHaveAttribute('href', '/instructors');
    expect(crumbs().getByText('추순자')).toBeInTheDocument();
  });

  it('없는 강사 번호는 찾을 수 없음이다', async () => {
    renderApp('/instructors/999');
    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });
});

describe('모집공고', () => {
  it('상태·공고명·모집기간·모집인원 표와 지원내역 링크를 그린다', async () => {
    renderApp('/instructors/recruit');

    expect(await screen.findByRole('heading', { level: 1, name: '강사등록신청' })).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: '강사 모집공고' });
    expect(within(table).getAllByRole('columnheader').map((c) => c.textContent)).toEqual(['상태', '모집공고', '모집기간', '모집인원']);
    const closed = within(table).getAllByRole('row').find((row) => row.textContent?.includes('통기타 강사 모집'))!;
    expect(within(closed).getAllByRole('cell').map((c) => c.textContent)).toEqual([
      '모집마감',
      '2026년 조리읍 주민자치센터 통기타 강사 모집',
      '2026.02.23–03.13',
      '1명',
    ]);
    expect(within(closed).getByRole('link', { name: /통기타 강사 모집/ })).toHaveAttribute('href', '/instructors/recruit/1');
    expect(screen.getByRole('link', { name: '지원내역' })).toHaveAttribute('href', '/me/instructor-applications');
  });

  it('마감된 공고 상세는 모집 정보와 지원 안내를 보이고 지원하기를 보이지 않는다', async () => {
    renderApp('/instructors/recruit/1');

    expect(await screen.findByRole('heading', { level: 2, name: '2026년 조리읍 주민자치센터 통기타 강사 모집' })).toBeInTheDocument();
    expect(screen.getByText('2026.02.19 공고 · 모집마감')).toBeInTheDocument();
    expect(definition('모집기간')).toHaveTextContent('2026.02.23–03.13');
    expect(definition('모집인원')).toHaveTextContent('1명');
    expect(definition('모집분야')).toHaveTextContent('통기타');
    expect(screen.getByRole('heading', { level: 3, name: '지원안내' })).toBeInTheDocument();
    expect(screen.getByText('자격·제출서류·심사 세부사항은 공고 원본을 확인해야 합니다.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '온라인 지원서 작성' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '목록' })).toHaveAttribute('href', '/instructors/recruit');
  });

  it('모집중인 공고에만 온라인 지원서 작성 링크를 보인다', async () => {
    renderApp(`/instructors/recruit/${OPEN_ID}`);
    expect(await screen.findByRole('link', { name: '온라인 지원서 작성' })).toHaveAttribute('href', `/instructors/recruit/${OPEN_ID}/apply`);
    expect(screen.getByText(/모집중/)).toBeInTheDocument();
  });

  it('없는 공고 번호는 찾을 수 없음이다', async () => {
    renderApp('/instructors/recruit/999');
    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });
});

describe('강사 지원서', () => {
  it('로그인하지 않았으면 로그인으로 보낸다', async () => {
    const { router } = renderApp(`/instructors/recruit/${OPEN_ID}/apply`);
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
  });

  it('이름·마스킹된 휴대전화와 입력 칸을 보이고 증빙 파일 칸은 두지 않는다', async () => {
    await signInAsDemo();
    renderApp(`/instructors/recruit/${OPEN_ID}/apply`);

    expect(await screen.findByRole('heading', { level: 1, name: '강사 지원서' })).toBeInTheDocument();
    expect(await screen.findByText('010-****-0000')).toBeInTheDocument();
    expect(definition('이름')).toHaveTextContent('예시회원');
    const field = screen.getByLabelText('희망 분야');
    expect(within(field).getAllByRole('option').map((o) => o.textContent)).toEqual(['컴퓨터', '어학/교양', '생활체육/건강', '문화/취미']);
    expect(screen.queryByLabelText(/증빙/)).not.toBeInTheDocument();
  });

  it('비어 있는 항목은 서버에 묻지 않고 칸마다 안내한다', async () => {
    await signInAsDemo();
    renderApp(`/instructors/recruit/${OPEN_ID}/apply`);
    await user().click(await screen.findByRole('button', { name: '신청' }));

    expect(screen.getByLabelText('희망 강좌명')).toHaveAccessibleDescription('희망 강좌명을 입력해 주세요.');
    expect(screen.getByLabelText('경력 및 강의소개')).toHaveAccessibleDescription('경력 및 강의소개를 입력해 주세요.');
    expect(screen.getByText('제출 내용을 확인해 주세요.')).toBeInTheDocument();
  });

  it('신청하면 지원내역으로 가서 서류 검토중 상태를 보이고 요청에 멱등키를 싣는다', async () => {
    await signInAsDemo();
    const keys: Array<string | null> = [];
    const listener = ({ request }: { request: Request }) => {
      if (request.method === 'POST' && new URL(request.url).pathname === '/api/v1/me/instructor-applications') {
        keys.push(request.headers.get('Idempotency-Key'));
      }
    };
    server.events.on('request:start', listener);
    let router: ReturnType<typeof renderApp>['router'];
    try {
      ({ router } = renderApp(`/instructors/recruit/${OPEN_ID}/apply`));
      const u = user();
      await u.selectOptions(await screen.findByLabelText('희망 분야'), '생활체육/건강');
      await fillApplication(u);
      await u.click(screen.getByRole('button', { name: '신청' }));
      await screen.findByRole('heading', { level: 1, name: '강사신청내역' });
    } finally {
      server.events.removeListener('request:start', listener);
    }

    expect(router.state.location.pathname).toBe('/me/instructor-applications');
    expect(keys).toHaveLength(1);
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
    expect(definition('지원 강좌')).toHaveTextContent('요가 심화반');
    expect(definition('처리상태')).toHaveTextContent('서류 검토중');
    expect(definition('지원자')).toHaveTextContent('예시회원');
    expect(screen.getByRole('link', { name: '지원서 수정' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '모집공고' })).toHaveAttribute('href', '/instructors/recruit');
  });

  it('화면이 갱신되기 전에 연달아 제출해도 한 번만 보낸다', async () => {
    await signInAsDemo();
    let calls = 0;
    const listener = ({ request }: { request: Request }) => {
      if (request.method === 'POST' && new URL(request.url).pathname === '/api/v1/me/instructor-applications') calls += 1;
    };
    server.events.on('request:start', listener);
    try {
      renderApp(`/instructors/recruit/${OPEN_ID}/apply`);
      await fillApplication(user());
      const form = screen.getByRole('form', { name: '강사 지원서' }) as HTMLFormElement;
      act(() => {
        form.requestSubmit();
        form.requestSubmit();
      });
      await screen.findByRole('heading', { level: 1, name: '강사신청내역' });
    } finally {
      server.events.removeListener('request:start', listener);
    }
    expect(calls).toBe(1);
  });

  it('이미 지원한 공고는 공고 화면에서 지원 링크 대신 안내를 보인다', async () => {
    await signInAsDemo();
    const view = renderApp(`/instructors/recruit/${OPEN_ID}/apply`);
    await fillApplication(user());
    await user().click(screen.getByRole('button', { name: '신청' }));
    await screen.findByRole('heading', { level: 1, name: '강사신청내역' });
    view.unmount();

    renderApp(`/instructors/recruit/${OPEN_ID}`);
    expect(await screen.findByText('이미 지원한 공고입니다.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '온라인 지원서 작성' })).not.toBeInTheDocument();
  });

  it('모집중이 아닌 공고에 직접 지원하면 서버 문구를 알린다', async () => {
    await signInAsDemo();
    renderApp('/instructors/recruit/1/apply');
    await fillApplication(user());
    await user().click(screen.getByRole('button', { name: '신청' }));
    expect(await screen.findByText('모집중인 공고만 지원할 수 있습니다.')).toHaveClass('is-error');
  });
});

describe('내 지원내역', () => {
  it('지원이 없으면 안내와 모집공고 링크를 보인다', async () => {
    await signInAsDemo();
    renderApp('/me/instructor-applications');
    expect(await screen.findByText('지원내역이 없습니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '모집공고' })).toHaveAttribute('href', '/instructors/recruit');
  });

  it('지원서를 고치면 저장되고 지원내역에 반영된다', async () => {
    await signInAsDemo();
    const view = renderApp(`/instructors/recruit/${OPEN_ID}/apply`);
    const u = user();
    await fillApplication(u);
    await u.click(screen.getByRole('button', { name: '신청' }));
    await screen.findByRole('heading', { level: 1, name: '강사신청내역' });
    await u.click(screen.getByRole('link', { name: '지원서 수정' }));

    const course = await screen.findByLabelText('희망 강좌명');
    expect(course).toHaveValue('요가 심화반');
    await u.clear(course);
    await u.type(course, '요가 입문반');
    await u.click(screen.getByRole('checkbox', { name: '제출 내용을 확인했습니다.' }));
    await u.click(screen.getByRole('button', { name: '저장' }));

    await screen.findByRole('heading', { level: 1, name: '강사신청내역' });
    expect(definition('지원 강좌')).toHaveTextContent('요가 입문반');
    view.unmount();
  });

  it('심사가 진행되어 고칠 수 없으면 수정 링크를 보이지 않는다', async () => {
    await signInAsDemo();
    server.use(
      http.get('/api/v1/me/instructor-applications', () =>
        HttpResponse.json({
          items: [
            {
              applicationId: '5000000000000000000001',
              recruitmentId: '2',
              recruitmentTitle: '요가 강사 모집',
              desiredCourse: '요가 심화반',
              categoryId: '3',
              categoryName: '생활체육/건강',
              career: '경력',
              status: 'SELECTED',
              appliedAt: '2026-09-08T10:00:00+09:00',
              canEdit: false,
            },
          ],
          page: 1,
          size: 10,
          total: 1,
          criteria: { basisAt: '2026-09-08T10:00:00+09:00', description: null },
        }),
      ),
    );
    renderApp('/me/instructor-applications');
    expect(await screen.findByText('선정')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '지원서 수정' })).not.toBeInTheDocument();
  });
});
