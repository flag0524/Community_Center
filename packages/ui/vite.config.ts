// CSS 진입점 두 개가 폰트와 시안 CSS를 빠짐없이 묶는지 확인하는 빌드 설정
import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        user: 'src/styles/entry-user.css',
        admin: 'src/styles/entry-admin.css',
      },
    },
  },
});
