// 운영 빌드 산출물에서 개발에서만 쓰는 파일을 지우는 함수. 사진은 사용 허가를 확인하기 전까지 배포하지 않는다
import { rmSync } from 'node:fs';
import { join } from 'node:path';

// public/ 아래 파일은 Vite가 그대로 복사하므로 빌드가 끝난 뒤에 지운다.
export const DEV_ONLY_PATHS = ['dev-assets', 'mockServiceWorker.js'];

export function stripDevOnly(outDir: string): void {
  for (const relative of DEV_ONLY_PATHS) {
    rmSync(join(outDir, relative), { recursive: true, force: true });
  }
}
