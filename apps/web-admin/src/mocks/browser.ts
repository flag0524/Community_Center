// 개발 서버에서 서비스 워커로 API 요청을 가로채는 모의 서버 시작 코드
import { setupWorker } from 'msw/browser';
import { initMockIdleFromLocation } from './auth';
import { handlers } from './handlers';

export async function startMockServer(): Promise<void> {
  initMockIdleFromLocation();
  await setupWorker(...handlers).start({ onUnhandledFrame: 'bypass', quiet: true });
}