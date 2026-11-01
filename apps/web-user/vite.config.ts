// 주민 앱의 Vite 설정. 개발 서버의 API 프록시, 운영 빌드의 개발 전용 파일 제거, Vitest 환경을 함께 정의한다
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
import { defineConfig, type Plugin } from 'vitest/config';
import { findDevLeaks, stripDevOnly } from './src/build/stripDevOnly.ts';

function stripDevOnlyPlugin(): Plugin {
  let outDir = '';
  return {
    name: 'jori-strip-dev-only',
    apply: 'build',
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    closeBundle() {
      stripDevOnly(outDir);
      const leaks = findDevLeaks(outDir);
      if (leaks.length > 0) {
        throw new Error(`운영 빌드에 개발 전용 코드가 섞였습니다. ${leaks.join(', ')}`);
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), stripDevOnlyPlugin()],
  server: {
    // 모의 API(MSW)를 끄고 실제 백엔드를 쓸 때 사용한다.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
});
