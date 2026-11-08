// 운영 빌드 산출물에서 개발에서만 쓰는 파일을 지우고, 모의 서버 코드가 번들에 새지 않았는지 검사하는 함수
import { readdirSync, readFileSync, rmSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

// public/ 아래 파일은 Vite가 그대로 복사하므로 빌드가 끝난 뒤에 지운다. 청사 사진은 사용 허가를 확인하기 전까지 배포하지 않는다.
export const DEV_ONLY_PATHS = ['dev-assets', 'mockServiceWorker.js'];

// 번들에 이 문자열이 있으면 모의 서버나 시계 조절 기능이 운영 빌드에 섞인 것이다.
export const DEV_ONLY_MARKERS = ['mockServiceWorker', 'mockNow', 'mockPay', 'mockHome', 'setupWorker', 'Demo-pass-2026'];

const SCANNED = /\.(js|mjs|html)$/;

export function stripDevOnly(outDir: string): void {
  for (const path of DEV_ONLY_PATHS) {
    rmSync(join(outDir, path), { recursive: true, force: true });
  }
}

function listFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    return entry.isDirectory() ? listFiles(full) : [full];
  });
}

/** 개발 전용 표지가 들어 있는 산출물을 '경로 (표지)' 형태로 모아 돌려준다. 없으면 빈 배열이다. */
export function findDevLeaks(outDir: string): string[] {
  const leaks: string[] = [];
  for (const file of listFiles(outDir).filter((name) => SCANNED.test(name))) {
    const text = readFileSync(file, 'utf8');
    for (const marker of DEV_ONLY_MARKERS) {
      if (text.includes(marker)) leaks.push(`${relative(outDir, file).split(sep).join('/')} (${marker})`);
    }
  }
  return leaks.sort();
}
