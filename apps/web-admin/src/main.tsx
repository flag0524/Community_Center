// 관리자 앱 진입점. 개발 서버에서는 모의 API를 먼저 켜고 라우터와 서버 상태 저장소를 연결한다
import '@jori/ui/admin.css';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider, createBrowserRouter } from 'react-router-dom';
import { routes } from './app/routes';
import './app.css';

async function bootstrap(): Promise<void> {
  // 실제 백엔드를 쓰려면 VITE_API_MODE=live 로 실행한다. 운영 빌드에는 모의 서버가 들어가지 않는다.
  if (import.meta.env.DEV && import.meta.env.VITE_API_MODE !== 'live') {
    try {
      const { startMockServer } = await import('./mocks/browser');
      await startMockServer();
    } catch (error) {
      console.warn('모의 서버를 시작하지 못했습니다.', error);
    }
  }

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
  });
  const router = createBrowserRouter(routes);
  const container = document.getElementById('root');
  if (!container) throw new Error('root 요소를 찾을 수 없습니다.');

  createRoot(container).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
}

void bootstrap();