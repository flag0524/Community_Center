// 질문과 답변(문의)과 수강후기의 목록·상세·작성·수정·삭제와 내 문의·내 후기가 서버 판정대로 동작하는지 확인하는 시험
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createApplication } from '../../api/applications';
import { confirmPayment, requestPayment } from '../../api/payments';
import { setMockNow } from '../../mocks/clock';
import { renderApp, server, signInAsDemo, useMockServer } from '../../test/render';

useMockServer();

const DURING = new Date('2026-09-08T10:00:00+09:00');
beforeEach(() => setMockNow(DURING));
afterEach(() => setMockNow(null));

const user = () => userEvent.setup({ delay: null });
const row = (table: HTMLElement, text: string) => within(table).getAllByRole('row').find((r) => r.textContent?.includes(text))!;

/** 유료 강좌를 신청하고 결제까지 끝내 수강확정 상태로 만든다. */
async function confirmedCourse() {
  const application = await createApplication('1', crypto.randomUUID());
  const request = await requestPayment(application.applicationId, 'CARD', crypto.randomUUID());
  await confirmPayment({ orderNo: request.orderNo, paymentKey: 'key', amount: request.amount });
}

describe('질문과 답변', () => {
  it('로그인하지 않았으면 로그인으로 보낸다', async () => {
    const { router } = renderApp('/board/qna');
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent('/board/qna')}`);
  });

  it('분류·제목·작성자·상태 표를 그리고 다른 회원의 비공개 문의는 서버가 가린 값 그대로 링크 없이 보인다', async () => {
    await signInAsDemo();
    renderApp('/board/qna');

    expect(await screen.findByRole('heading', { level: 1, name: '질문과 답변' })).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: '문의 목록' });
    expect(within(table).getAllByRole('columnheader').map((c) => c.textContent)).toEqual(['분류', '제목', '작성자', '상태']);
    const mine = row(table, '결제 결과는 어디서 확인하나요?');
    expect(within(mine).getByRole('link', { name: '결제 결과는 어디서 확인하나요?' })).toHaveAttribute('href', '/board/qna/601');
    expect(within(mine).getByText('답변완료')).toBeInTheDocument();
    expect(within(row(table, '대기신청 순번 문의')).getByText('접수')).toBeInTheDocument();
    const hidden = row(table, '비공개 문의입니다.');
    expect(within(hidden).queryByRole('link')).not.toBeInTheDocument();
    expect(within(hidden).getByText('김**')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '문의 작성' })).toHaveAttribute('href', '/board/qna/write');
    expect(screen.getByRole('link', { name: '내 문의' })).toHaveAttribute('href', '/me/inquiries');
    expect(document.title).toBe('질문과 답변 | 조리읍주민자치센터');
  });

  it('상세는 본문과 센터 답변, 비공개 표시를 보이고 답변이 달린 문의는 수정할 수 없다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/601');

    expect(await screen.findByRole('heading', { level: 2, name: '결제 결과는 어디서 확인하나요?' })).toBeInTheDocument();
    expect(screen.getByText(/예시회원 · 2026\.10\.06 · 비공개/)).toBeInTheDocument();
    expect(screen.getByText(/수강료 결제를 진행했습니다/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: '센터 답변' })).toBeInTheDocument();
    expect(screen.getByText(/마이페이지의 신청 상세에서 결제상태를 확인하실 수 있습니다/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '수정' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '삭제' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '목록' })).toHaveAttribute('href', '/board/qna');
  });

  it('답변 전의 본인 문의는 수정 링크를 보이고 답변 대기 안내를 보인다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/602');
    expect(await screen.findByRole('link', { name: '수정' })).toHaveAttribute('href', '/board/qna/602/edit');
    expect(screen.getByText('아직 답변이 등록되지 않았습니다.')).toBeInTheDocument();
  });

  it('다른 회원의 비공개 문의는 찾을 수 없음이고 공개 문의는 볼 수 있다', async () => {
    await signInAsDemo();
    const first = renderApp('/board/qna/603');
    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
    first.unmount();
    renderApp('/board/qna/604');
    expect(await screen.findByRole('heading', { level: 2, name: '수강 시간 문의' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '수정' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '삭제' })).not.toBeInTheDocument();
  });

  it('삭제는 확인 단계를 거치고 삭제하면 목록으로 돌아가 사라진다', async () => {
    await signInAsDemo();
    const { router } = renderApp('/board/qna/602');
    const u = user();
    await u.click(await screen.findByRole('button', { name: '삭제' }));
    const confirm = screen.getByRole('group', { name: '문의 삭제 확인' });
    await u.click(within(confirm).getByRole('button', { name: '돌아가기' }));
    expect(screen.queryByRole('group', { name: '문의 삭제 확인' })).not.toBeInTheDocument();

    await u.click(screen.getByRole('button', { name: '삭제' }));
    await u.click(within(screen.getByRole('group', { name: '문의 삭제 확인' })).getByRole('button', { name: '삭제하기' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/board/qna'));
    const table = await screen.findByRole('table', { name: '문의 목록' });
    expect(within(table).queryByText('대기신청 순번 문의')).not.toBeInTheDocument();
  });

  it('문의를 쓰면 분류 목록은 서버 값이고 비공개가 기본이며 등록하면 상세로 간다', async () => {
    await signInAsDemo();
    const { router } = renderApp('/board/qna/write');
    const u = user();
    const category = await screen.findByLabelText('문의 분류');
    expect(within(category).getAllByRole('option').map((o) => o.textContent)).toEqual(['수강신청', '결제', '환불', '센터 이용']);
    expect(screen.getByRole('checkbox', { name: '비공개 문의' })).toBeChecked();
    await u.selectOptions(category, '환불');
    await u.type(screen.getByLabelText('제목'), '환불 문의');
    await u.type(screen.getByLabelText('내용'), '환불은 어떻게 하나요?');
    await u.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/board\/qna\/[0-9]+$/));
    expect(await screen.findByRole('heading', { level: 2, name: '환불 문의' })).toBeInTheDocument();
    expect(screen.getByText(/예시회원 · .* · 비공개/)).toBeInTheDocument();
  });

  it('제목이나 내용이 비어 있으면 서버에 묻지 않고 칸마다 안내한다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/write');
    await user().click(await screen.findByRole('button', { name: '등록' }));
    expect(screen.getByLabelText('제목')).toHaveAccessibleDescription('제목을 입력해 주세요.');
    expect(screen.getByLabelText('내용')).toHaveAccessibleDescription('내용을 입력해 주세요.');
  });

  it('등록 요청에 멱등키를 싣고 눌러도 한 번만 보낸다', async () => {
    await signInAsDemo();
    const seen: Array<{ key: string | null }> = [];
    const listener = ({ request }: { request: Request }) => {
      if (request.method === 'POST' && new URL(request.url).pathname === '/api/v1/me/inquiries') {
        seen.push({ key: request.headers.get('Idempotency-Key') });
      }
    };
    server.events.on('request:start', listener);
    try {
      renderApp('/board/qna/write');
      const u = user();
      await u.type(await screen.findByLabelText('제목'), '제목');
      await u.type(screen.getByLabelText('내용'), '내용');
      await u.dblClick(screen.getByRole('button', { name: '등록' }));
      await screen.findByRole('heading', { level: 2, name: '제목' });
    } finally {
      server.events.removeListener('request:start', listener);
    }
    expect(seen).toHaveLength(1);
    expect(seen[0]!.key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('화면이 갱신되기 전에 연달아 제출해도 문의는 한 번만 보낸다', async () => {
    await signInAsDemo();
    let calls = 0;
    const listener = ({ request }: { request: Request }) => {
      if (request.method === 'POST' && new URL(request.url).pathname === '/api/v1/me/inquiries') calls += 1;
    };
    server.events.on('request:start', listener);
    try {
      renderApp('/board/qna/write');
      const u = user();
      await u.type(await screen.findByLabelText('제목'), '제목');
      await u.type(screen.getByLabelText('내용'), '내용');
      const form = screen.getByRole('form', { name: '문의' }) as HTMLFormElement;
      // 한 번의 act 안에서 두 번 제출하면 그 사이에 화면이 다시 그려지지 않는다.
      act(() => {
        form.requestSubmit();
        form.requestSubmit();
      });
      await screen.findByRole('heading', { level: 2, name: '제목' });
    } finally {
      server.events.removeListener('request:start', listener);
    }
    expect(calls).toBe(1);
  });

  it('수정 화면은 기존 값을 채우고 저장하면 상세에 반영한다', async () => {    await signInAsDemo();
    const { router } = renderApp('/board/qna/602/edit');
    const u = user();
    const title = await screen.findByLabelText('제목');
    expect(title).toHaveValue('대기신청 순번 문의');
    await u.clear(title);
    await u.type(title, '순번을 알고 싶어요');
    await u.click(screen.getByRole('button', { name: '수정' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/board/qna/602'));
    expect(await screen.findByRole('heading', { level: 2, name: '순번을 알고 싶어요' })).toBeInTheDocument();
  });

  it('답변이 달린 문의를 직접 수정하려 하면 서버 문구를 알린다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/601/edit');
    const u = user();
    await u.click(await screen.findByRole('button', { name: '수정' }));
    expect(await screen.findByText('답변이 달린 문의는 고칠 수 없습니다.')).toHaveClass('is-error');
  });
});

describe('내 문의', () => {
  it('내가 쓴 문의만 제목과 상태로 보인다', async () => {
    await signInAsDemo();
    renderApp('/me/inquiries');

    expect(await screen.findByRole('heading', { level: 1, name: '내 문의' })).toBeInTheDocument();
    const link = await screen.findByRole('link', { name: /결제 결과는 어디서 확인하나요\?/ });
    expect(link).toHaveAttribute('href', '/board/qna/601');
    expect(within(link).getByText('답변완료')).toBeInTheDocument();
    expect(screen.queryByText('수강 시간 문의')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '문의 작성' })).toHaveAttribute('href', '/board/qna/write');
  });
});

describe('수강후기', () => {
  it('누구나 후기 목록을 보고 후기 작성·내 후기 링크가 있다', async () => {
    renderApp('/board/review');

    expect(await screen.findByRole('heading', { level: 1, name: '수강후기' })).toBeInTheDocument();
    expect(await screen.findByText('등록된 후기가 없습니다.')).toBeInTheDocument();
    expect(screen.getByRole('search', { name: '수강후기 검색' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '수강후기 작성' })).toHaveAttribute('href', '/board/review/write');
    expect(screen.getByRole('link', { name: '내 후기 확인' })).toHaveAttribute('href', '/me/reviews');
  });

  it('수강확정이 아니면 후기 작성 화면은 쓸 수 없다고 안내하고 양식을 보이지 않는다', async () => {
    await signInAsDemo();
    renderApp('/board/review/write');
    expect(await screen.findByText('후기를 쓸 수 있는 수강확정 강좌가 없습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '등록' })).not.toBeInTheDocument();
  });

  it('수강확정 강좌의 후기를 쓰고 목록·상세·내 후기에서 보고 수정·삭제한다', async () => {
    await signInAsDemo();
    await confirmedCourse();
    const { router } = renderApp('/board/review/write');
    const u = user();
    const course = await screen.findByLabelText('수강 강좌');
    expect(within(course).getAllByRole('option').map((o) => o.textContent)).toEqual(['초급컴퓨터']);
    await u.type(screen.getByLabelText('제목'), '초급컴퓨터 후기');
    await u.type(screen.getByLabelText('내용'), '차근차근 알려 주셔서 좋았어요.');
    await u.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/board\/review\/[0-9]+$/));
    expect(await screen.findByRole('heading', { level: 2, name: '초급컴퓨터 후기' })).toBeInTheDocument();
    expect(screen.getByText(/예시회원 · /)).toBeInTheDocument();
    expect(screen.getByText('수강 강좌 초급컴퓨터')).toBeInTheDocument();
    const id = router.state.location.pathname.split('/')[3]!;

    // 목록과 내 후기에 나타난다.
    await router.navigate('/board/review');
    const table = await screen.findByRole('table', { name: '수강후기 목록' });
    expect(within(table).getByRole('link', { name: '초급컴퓨터 후기' })).toHaveAttribute('href', `/board/review/${id}`);
    await router.navigate('/me/reviews');
    await screen.findByRole('heading', { level: 1, name: '내 수강후기' });
    expect(await screen.findByRole('link', { name: /초급컴퓨터 후기/ })).toBeInTheDocument();

    // 수정한다.
    await router.navigate(`/board/review/${id}/edit`);
    const title = await screen.findByLabelText('제목');
    await u.clear(title);
    await u.type(title, '수정한 후기');
    await u.click(screen.getByRole('button', { name: '수정' }));
    expect(await screen.findByRole('heading', { level: 2, name: '수정한 후기' })).toBeInTheDocument();

    // 삭제한다.
    await u.click(screen.getByRole('button', { name: '삭제' }));
    await u.click(within(screen.getByRole('group', { name: '후기 삭제 확인' })).getByRole('button', { name: '삭제하기' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/board/review'));
    expect(await screen.findByText('등록된 후기가 없습니다.')).toBeInTheDocument();
  });

  it('수강확정이 아닌 강좌로 직접 후기를 쓰려 하면 서버가 거절한다', async () => {
    await signInAsDemo();
    server.use(
      http.get('/api/v1/me/reviewable-courses', () => HttpResponse.json({ items: [{ courseId: '2', name: '생활영어' }] })),
    );
    renderApp('/board/review/write');
    const u = user();
    await u.type(await screen.findByLabelText('제목'), '제목');
    await u.type(screen.getByLabelText('내용'), '내용');
    await u.click(screen.getByRole('button', { name: '등록' }));
    expect(await screen.findByText('수강확정인 강좌의 후기만 쓸 수 있습니다.')).toHaveClass('is-error');
  });

  it('후기 검색은 주소에 검색어를 남긴다', async () => {
    const { router } = renderApp('/board/review');
    const u = user();
    await u.type(await screen.findByLabelText('제목으로 검색'), '컴퓨터');
    await u.click(within(screen.getByRole('search', { name: '수강후기 검색' })).getByRole('button', { name: '검색' }));
    await waitFor(() => expect(router.state.location.search).toBe('?q=%EC%BB%B4%ED%93%A8%ED%84%B0'));
  });
});
