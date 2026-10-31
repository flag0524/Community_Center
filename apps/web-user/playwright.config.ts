// 실제 브라우저 시험 설정. 별도 브라우저 내려받기 없이 이 PC에 설치된 Edge를 쓴다
import { defineConfig } from '@playwright/test';

const PORT = 5273;

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: true,
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
