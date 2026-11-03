// 실제 브라우저 시험 설정. 별도 브라우저 내려받기 없이 이 PC에 설치된 Edge를 쓴다
import { defineConfig } from '@playwright/test';

const PORT = 5273;

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: true,
  // 시험이 100개에 가까워지자 4개를 동시에 돌리면 Edge가 "Target crashed"로 죽거나 개발 서버 연결이 끊겼다.
  // 단독 실행과 2개 동시 실행은 모두 통과했으므로 시험 논리가 아니라 자원 경합이라 보고 2개로 제한한다.
  workers: 2,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    channel: 'msedge',
    serviceWorkers: 'allow',
  },
  webServer: {
    command: `pnpm exec vite --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
