// 개발 서버에서 서비스 워커로 API 요청을 가로채는 모의 서버 시작 코드
import { setupWorker } from 'msw/browser';
import { initMockClockFromLocation } from './clock';
import { handlers } from './handlers';
import { initMockPayFromLocation } from './payOutcome';

export async function startMockServer(): Promise<void> {
  initMockClockFromLocation();
  initMockPayFromLocation();
  await setupWorker(...handlers).start({ onUnhandledFrame: 'bypass', quiet: true });
}
