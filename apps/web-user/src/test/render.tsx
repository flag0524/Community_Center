// 라우터와 서버 상태 저장소를 갖춘 채 앱을 그리는 시험 도우미와 모의 서버 준비 코드
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { setupServer } from 'msw/node';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { login } from '../api/auth';
import { rememberCsrfToken } from '../api/http';
import { routes } from '../app/routes';
import { resetMockApplications } from '../mocks/applications';
import { DEMO, resetMockAuth } from '../mocks/auth';
import { resetMockCommunity } from '../mocks/community';
import { handlers } from '../mocks/handlers';
import { resetMockInstructors } from '../mocks/instructors';

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
    resetMockApplications();
    resetMockCommunity();
    resetMockInstructors();
    rememberCsrfToken(null);
  });
  afterAll(() => server.close());
}

/** 모의 서버에 시험 계정으로 로그인해 둔다. 이어서 renderApp을 하면 앱이 로그인 상태로 시작한다. */
export async function signInAsDemo(): Promise<void> {
  await login({ loginId: DEMO.loginId, password: DEMO.password });
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
