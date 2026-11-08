// 감면 사전심사 신청·결과(내역, 신청 규칙, 증빙 올리기와 접수 상태에서만 바뀌는 잠금, 철회)가 서버 판정대로 그려지는지 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { ApiRequestError } from '../../api/http';
import { renderApp, server, signInAsDemo, useMockServer } from '../../test/render';

// jsdom의 FormData는 Node의 fetch로 보낼 수 없어 올리기만 모의 서버의 검사 규칙으로 바로 연결한다. 실제 multipart 전송은 브라우저 시험이 확인한다.
vi.mock('../../api/myFiles', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/myFiles')>();
  const { receiveUpload } = await import('../../mocks/files');
  const { currentMockMember } = await import('../../mocks/auth');
  return {
    ...original,
    uploadMyFile: async (ownerPath: string, file: File) => {
      const result = receiveUpload(ownerPath, currentMockMember()!.memberId, { name: file.name, size: file.size });
      if ('file' in result) return result.file;
      throw new ApiRequestError(result.status, { code: result.code, message: '요청을 처리하지 못했습니다.', fields: result.fields ?? {}, requestId: 'test' });
    },
  };
});
useMockServer();

const definition = (term: string) => screen.getByText(term, { selector: 'dt' }).nextElementSibling as HTMLElement;
const FOURTH = '1000000000000000000001';

async function apply(cycle: string, type: string) {
  await userEvent.selectOptions(await screen.findByLabelText('교육기수'), cycle);
  if (type) await userEvent.click(screen.getByLabelText(type));
  await userEvent.click(screen.getByRole('button', { name: '신청' }));
}

describe('감면 심사 내역', () => {
  it('신청한 심사를 최근 신청부터 기수·유형·상태와 함께 보인다', async () => {
    await signInAsDemo();
    renderApp('/me/reductions');
    const headings = await screen.findAllByRole('heading', { level: 2 });
    expect(headings.map((heading) => heading.textContent)).toEqual(['2027년 제1기 · 국가유공자 본인', '2026년 제4기 · 기초생활보장 수급자 본인']);
    expect(within(screen.getByRole('main')).getAllByRole('status').map((status) => status.textContent)).toEqual(['승인', '반려']);
    expect(screen.getAllByRole('link', { name: '상세 보기' }).map((link) => link.getAttribute('href'))).toEqual(['/me/reductions/5002', '/me/reductions/5001']);
  });

  it('감면 신청 링크와 마이페이지 메뉴를 보인다', async () => {
    await signInAsDemo();
    renderApp('/me/reductions');
    expect(await screen.findByRole('link', { name: '감면 신청' })).toHaveAttribute('href', '/me/reductions/new');
  });

  it('서버가 신청할 수 없다고 알리면 이유를 보이고 신청 링크를 숨긴다', async () => {
    server.use(http.get('/api/v1/me/reduction-options', () => HttpResponse.json({ cycles: [], canApply: false, blockReason: '조리읍 거주 확인이 필요합니다.' })));
    await signInAsDemo();
    renderApp('/me/reductions');
    expect(await screen.findByText('조리읍 거주 확인이 필요합니다.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '감면 신청' })).not.toBeInTheDocument();
  });
});

describe('감면 신청', () => {
  it('기수와 유형을 골라 신청하면 접수 상태의 상세로 가고 증빙을 올리라고 안내한다', async () => {
    await signInAsDemo();
    const { router } = renderApp('/me/reductions/new');
    await apply('2026년 제4기', '등록 장애인 본인');
    expect(await screen.findByText('신청했습니다. 아래에서 증빙 파일을 올려 주세요.')).toBeInTheDocument();
    expect(router.state.location.pathname).toMatch(/^\/me\/reductions\/50\d+$/);
    expect(definition('심사 상태')).toHaveTextContent('접수');
    expect(definition('감면 유형')).toHaveTextContent('등록 장애인 본인');
    expect(await screen.findByText('올린 파일이 없습니다.')).toBeInTheDocument();
  });

  it('유형을 고르지 않으면 요청 없이 안내한다', async () => {
    let calls = 0;
    server.use(
      http.post('/api/v1/me/reduction-reviews', () => {
        calls += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
    );
    await signInAsDemo();
    renderApp('/me/reductions/new');
    await apply('2026년 제4기', '');
    expect(await screen.findByText('감면 유형을 선택해 주세요.')).toBeInTheDocument();
    expect(calls).toBe(0);
  });

  it('이미 승인된 기수에는 신청할 수 없다는 서버 답을 보인다', async () => {
    await signInAsDemo();
    renderApp('/me/reductions/new');
    await apply('2027년 제1기', '국가유공자 본인');
    expect(await screen.findByText('이 기수에는 이미 접수되었거나 승인된 심사가 있습니다.')).toBeInTheDocument();
  });

  it('요청에는 기수와 유형만 싣고 금액·비율은 보내지 않으며 멱등키를 함께 보낸다', async () => {
    let sent: { body?: Record<string, unknown>; key: string | null } = { key: null };
    server.use(
      http.post('/api/v1/me/reduction-reviews', async ({ request }) => {
        sent = { body: (await request.json()) as Record<string, unknown>, key: request.headers.get('Idempotency-Key') };
        return HttpResponse.json({ code: 'RULE_REJECTED', message: '시험용 거절', fields: null, requestId: 'r' }, { status: 422 });
      }),
    );
    await signInAsDemo();
    renderApp('/me/reductions/new');
    await apply('2026년 제4기', '기초생활보장 수급자 본인');
    await screen.findByText('시험용 거절');
    expect(sent.body).toEqual({ cycleId: FOURTH, reductionType: 'LIVELIHOOD' });
    expect(sent.key).toBeTruthy();
  });

  it('거주 확인이 안 된 회원은 신청 양식 대신 이유를 본다', async () => {
    server.use(http.get('/api/v1/me/reduction-options', () => HttpResponse.json({ cycles: [], canApply: false, blockReason: '조리읍 거주 확인이 필요합니다.' })));
    await signInAsDemo();
    renderApp('/me/reductions/new');
    expect(await screen.findByText('조리읍 거주 확인이 필요합니다.')).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: '감면 신청' })).not.toBeInTheDocument();
  });
});

describe('감면 심사 상세', () => {
  it('반려된 심사는 사유를 보이고 증빙이 잠겨 있으며 철회할 수 없다', async () => {
    await signInAsDemo();
    renderApp('/me/reductions/5001');
    expect(await screen.findByText('증빙 서류가 확인되지 않습니다.')).toBeInTheDocument();
    expect(definition('심사 상태')).toHaveTextContent('반려');
    expect(await screen.findByText('지금은 파일을 추가하거나 제거할 수 없습니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '증명서.pdf' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '신청 철회' })).not.toBeInTheDocument();
    expect(screen.getByText('반려된 신청은 고칠 수 없습니다. 다시 심사를 받으려면 새로 신청해 주세요.')).toBeInTheDocument();
  });

  it('승인된 심사는 유효 종료일을 보이고 증빙을 고칠 수 없다', async () => {
    await signInAsDemo();
    renderApp('/me/reductions/5002');
    await waitFor(() => expect(definition('승인 유효 종료일')).toHaveTextContent('2030-12-31'));
    expect(await screen.findByText('지금은 파일을 추가하거나 제거할 수 없습니다.')).toBeInTheDocument();
  });

  it('접수 상태에서 증빙을 올리면 상세에 쌓이고 목록의 증빙 건수에 반영된다', async () => {
    await signInAsDemo();
    renderApp('/me/reductions/new');
    await apply('2026년 제4기', '국가유공자 본인');
    await screen.findByText('올린 파일이 없습니다.');
    const file = new File(['x'], '증빙.pdf', { type: 'application/pdf' });
    await userEvent.upload(await screen.findByLabelText('파일 추가'), file);
    expect(await screen.findByText('증빙.pdf')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    const first = (await screen.findAllByRole('heading', { level: 2 }))[0]!.closest('section')!;
    expect(within(first).getByText('증빙').nextElementSibling).toHaveTextContent('1건');
  });
  it('접수 상태의 신청은 두 번 확인해 철회하고 철회하면 증빙이 잠긴다', async () => {
    await signInAsDemo();
    renderApp('/me/reductions/new');
    await apply('2026년 제4기', '국가유공자 본인');
    await userEvent.click(await screen.findByRole('button', { name: '신청 철회' }));
    expect(within(screen.getByRole('group', { name: '신청 철회 확인' })).getByText(/철회하면 증빙을 더 올릴 수 없고/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '철회하기' }));
    await waitFor(() => expect(definition('심사 상태')).toHaveTextContent('철회'));
    expect(screen.queryByRole('button', { name: '신청 철회' })).not.toBeInTheDocument();
    expect(await screen.findByText('지금은 파일을 추가하거나 제거할 수 없습니다.')).toBeInTheDocument();
  });

  it('철회 확인에서 돌아가면 신청은 그대로다', async () => {
    await signInAsDemo();
    renderApp('/me/reductions/new');
    await apply('2026년 제4기', '국가유공자 본인');
    await userEvent.click(await screen.findByRole('button', { name: '신청 철회' }));
    await userEvent.click(screen.getByRole('button', { name: '돌아가기' }));
    expect(definition('심사 상태')).toHaveTextContent('접수');
    expect(screen.getByRole('button', { name: '신청 철회' })).toBeInTheDocument();
  });

  it('남의 심사는 찾을 수 없다', async () => {
    await signInAsDemo();
    expect((await fetch('/api/v1/me/reduction-reviews/9999')).status).toBe(404);
  });

  it('철회가 서버에서 거절되면 사유를 보인다', async () => {
    server.use(http.post('/api/v1/me/reduction-reviews/:id/withdraw', () => HttpResponse.json({ code: 'CONFLICT_STATE', message: '이미 심사가 시작되었습니다.', requestId: 'r' }, { status: 409 })));
    await signInAsDemo();
    renderApp('/me/reductions/new');
    await apply('2026년 제4기', '국가유공자 본인');
    await userEvent.click(await screen.findByRole('button', { name: '신청 철회' }));
    await userEvent.click(screen.getByRole('button', { name: '철회하기' }));
    expect(await screen.findByText('이미 심사가 시작되었습니다.')).toBeInTheDocument();
  });
});