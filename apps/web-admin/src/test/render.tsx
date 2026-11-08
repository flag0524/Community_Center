// 라우터와 서버 상태 저장소를 갖춘 채 관리자 앱을 그리는 시험 도우미와 모의 서버 준비 코드
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { setupServer } from 'msw/node';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { login } from '../api/auth';
import { rememberCsrfToken } from '../api/http';
import { routes } from '../app/routes';
import { DEMO_ADMINS, resetMockAuth } from '../mocks/auth';
import { resetMockBoards } from '../mocks/boards';
import { resetMockCampus } from '../mocks/campus';
import { resetMockClasses } from '../mocks/classes';
import { resetMockContents } from '../mocks/contents';
import { resetMockFiles } from '../mocks/files';
import { resetMockTerms } from '../mocks/terms';
import { resetMockInquiries } from '../mocks/inquiries';
import { resetMockMembers } from '../mocks/members';
import { resetMockRefunds } from '../mocks/refunds';
import { resetMockReductions } from '../mocks/reductions';
import { resetMockRetention } from '../mocks/retention';
import { resetMockReview } from '../mocks/review';
import { resetMockRoles } from '../mocks/roles';
import { resetMockSettings } from '../mocks/settings';
import { resetMockSms } from '../mocks/sms';
import { resetExportLog } from '../mocks/csv';
import { resetMockPii } from '../mocks/pii';
import { resetMockTransactions } from '../mocks/transactions';
import { resetMockEducation } from '../mocks/education';
import { handlers } from '../mocks/handlers';

// Node의 fetch는 상대 경로를 받지 못한다. 브라우저처럼 현재 주소를 기준으로 풀어 준다.
const nativeFetch = globalThis.fetch.bind(globalThis);
globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) =>
  nativeFetch(typeof input === 'string' ? new URL(input, window.location.href) : input, init);

export const server = setupServer(...handlers);

/** 모의 서버를 시험 파일 수명에 맞춰 켜고 끈다. 처리기가 없는 요청은 시험을 실패시킨다. */
export function useMockServer(): void {
  beforeAll(() => server.listen({ onUnhandledFrame: 'error' }));
  afterEach(() => {
    server.resetHandlers();
    resetMockAuth();
    resetMockEducation();
    resetMockCampus();
    resetMockReview();
    resetMockRefunds();
    resetMockMembers();
    resetMockBoards();
    resetMockInquiries();
    resetMockContents();
    resetMockTerms();
    resetMockSms();
    resetMockRoles();
    resetMockReductions();
    resetMockSettings();
    resetMockClasses();
    resetMockRetention();
    resetMockFiles();
    resetMockTransactions();
    resetExportLog();
    resetMockPii();
    rememberCsrfToken(null);
  });
  afterAll(() => server.close());
}

/** 모의 서버에 시험 계정으로 로그인해 둔다. 이어서 renderApp을 하면 앱이 로그인 상태로 시작한다. */
export async function signInAs(role: keyof typeof DEMO_ADMINS = 'group'): Promise<void> {
  const { loginId, password } = DEMO_ADMINS[role];
  await login({ loginId, password });
}

export function renderApp(path = '/') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...view, router, queryClient };
}