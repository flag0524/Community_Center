// 화면(pages)을 주소로 들어갈 때 내려받도록 지연 로딩으로만 가져오는지 지키는 시험(진입 파일 크기, 코드 리뷰 성능 중-5)
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// 첫 화면·로그인 같이 처음부터 필요한 화면만 진입 파일에 함께 둔다
const EAGER = ['LoginPage', 'NotFoundPage'];
const FILES = ['./screens.tsx']; // routes.tsx에는 로그인·찾을 수 없음 화면만 있다

describe('라우트 코드 분할', () => {
  for (const file of FILES) {
    it(`${file}는 처음부터 필요한 화면 외에는 정적으로 import하지 않는다`, () => {
      const source = readFileSync(new URL(file, import.meta.url), 'utf8');
      const staticPages = [...source.matchAll(/^import \{ (\w+) \} from '\.\.\/pages\/[^']+';$/gm)].map((m) => m[1] ?? '');
      expect(staticPages.filter((name) => !EAGER.includes(name))).toEqual([]);
      expect(source).toMatch(/lazy\(\(\) => import\('\.\.\/pages\//);
    });
  }
});