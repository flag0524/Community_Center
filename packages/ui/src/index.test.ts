// 화면 모드 정의와 시안 CSS 이식 결과를 확인하는 시험
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { DEFAULT_VIEW_MODE, TEXT_SIZE_STEPS, VIEW_MODES, isViewMode } from './index';

const stylesDir = fileURLToPath(new URL('./styles/', import.meta.url));
const assetsDir = fileURLToPath(new URL('./assets/', import.meta.url));
const read = (name: string) => readFileSync(stylesDir + name, 'utf8');

describe('화면 모드', () => {
  it('기본 화면과 쉬운 화면만 허용한다', () => {
    expect(VIEW_MODES).toEqual(['standard', 'easy']);
    expect(DEFAULT_VIEW_MODE).toBe('standard');
    expect(isViewMode('easy')).toBe(true);
    expect(isViewMode('admin')).toBe(false);
    expect(isViewMode(undefined)).toBe(false);
  });

  it('글자 크기는 90~120%를 10% 단위로 제공한다', () => {
    expect(TEXT_SIZE_STEPS).toEqual([90, 100, 110, 120]);
  });
});

describe('시안 CSS 이식', () => {
  it('시안의 색 변수를 그대로 가진다', () => {
    expect(read('site.css')).toContain('--blue:#315ab8');
  });

  it('로컬 ttf 폰트 참조가 남아 있지 않다', () => {
    for (const name of ['site.css', 'admin.css', 'easy.css', 'prototype.css']) {
      expect(read(name), name).not.toContain('NotoSansKR.ttf');
      expect(read(name), name).not.toContain('@font-face');
    }
  });

  it('폰트 이름은 fontsource 가변 폰트를 가리킨다', () => {
    expect(read('site.css')).toContain("font-family:'Noto Sans KR Variable'");
    expect(read('admin.css')).toContain("font-family:'Noto Sans KR Variable'");
  });

  it('두 진입점이 폰트와 필요한 CSS를 모두 불러온다', () => {
    const user = read('entry-user.css');
    for (const part of [
      '@fontsource-variable/noto-sans-kr',
      './site.css',
      './easy.css',
      './prototype.css',
      './app-extras.css',
    ]) {
      expect(user).toContain(part);
    }
    const admin = read('entry-admin.css');
    expect(admin).toContain('@fontsource-variable/noto-sans-kr');
    expect(admin).toContain('./admin.css');
  });

  it('접근성 보정 파일은 주민용 진입점의 맨 마지막에 불러온다', () => {
    const imports = read('entry-user.css')
      .split('\n')
      .filter((line) => line.startsWith('@import'));
    expect(imports.at(-1)).toContain('./a11y-fixes.css');
    expect(read('a11y-fixes.css')).toContain('#596475');
  });

  it('가져온 자산은 로고와 SNS 아이콘뿐이다', () => {
    expect(readdirSync(assetsDir).sort()).toEqual([
      'paju-ci.jpg',
      'sns-facebook.png',
      'sns-kakao.png',
      'sns-youtube.png',
    ]);
  });
});
