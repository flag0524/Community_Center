// 화면 모드·글자 크기 규칙과, 첫 화면 전에 도는 public/view-mode.js가 같은 결과를 내는지 확인하는 시험
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_TEXT_SIZE,
  canStep,
  parseTextSize,
  resolveViewMode,
  rootFontSizePercent,
  stepTextSize,
} from './viewMode';

const fakeStorage = (value: string | null) => ({ getItem: () => value });
const throwingStorage = {
  getItem: () => {
    throw new Error('저장소 접근 차단');
  },
};

describe('resolveViewMode', () => {
  it('주소의 view 값이 저장된 값보다 우선한다', () => {
    expect(resolveViewMode('?view=easy', fakeStorage('standard'))).toBe('easy');
    expect(resolveViewMode('?view=standard', fakeStorage('easy'))).toBe('standard');
  });

  it('주소에 없거나 잘못된 값이면 저장된 값을 쓴다', () => {
    expect(resolveViewMode('', fakeStorage('easy'))).toBe('easy');
    expect(resolveViewMode('?view=admin', fakeStorage('easy'))).toBe('easy');
  });

  it('둘 다 없거나 저장소가 막혀 있으면 기본 화면이다', () => {
    expect(resolveViewMode('', fakeStorage(null))).toBe('standard');
    expect(resolveViewMode('', null)).toBe('standard');
    expect(resolveViewMode('', throwingStorage)).toBe('standard');
    expect(resolveViewMode('?view=%3Cscript%3E', fakeStorage('<script>'))).toBe('standard');
  });
});

describe('글자 크기', () => {
  it('90~120% 안에서 10% 단위로만 움직인다', () => {
    expect(stepTextSize(100, 10)).toBe(110);
    expect(stepTextSize(120, 10)).toBe(120);
    expect(stepTextSize(90, -10)).toBe(90);
    expect(stepTextSize(110, 0)).toBe(DEFAULT_TEXT_SIZE);
  });

  it('범위 끝에서는 더 움직일 수 없다고 알려 준다', () => {
    expect(canStep(90, -10)).toBe(false);
    expect(canStep(90, 10)).toBe(true);
    expect(canStep(120, 10)).toBe(false);
    expect(canStep(120, -10)).toBe(true);
  });

  it('저장된 값이 올바르지 않으면 기본값으로 돌아간다', () => {
    expect(parseTextSize('110')).toBe(110);
    expect(parseTextSize('105')).toBe(100);
    expect(parseTextSize('abc')).toBe(100);
    expect(parseTextSize(null)).toBe(100);
  });

  it('쉬운 화면은 기본 글자를 25% 키운 뒤 조절 값을 곱한다', () => {
    expect(rootFontSizePercent(100, 'standard')).toBe(100);
    expect(rootFontSizePercent(100, 'easy')).toBe(125);
    expect(rootFontSizePercent(120, 'easy')).toBe(150);
    expect(rootFontSizePercent(90, 'standard')).toBe(90);
  });
});

describe('public/view-mode.js 와 resolveViewMode 의 일치', () => {
  const script = readFileSync(join(import.meta.dirname, '../../public/view-mode.js'), 'utf8');
  const cases: { search: string; stored: string | null }[] = [
    { search: '', stored: null },
    { search: '?view=easy', stored: null },
    { search: '?view=standard', stored: 'easy' },
    { search: '?view=bogus', stored: 'easy' },
    { search: '', stored: 'easy' },
    { search: '', stored: 'weird' },
    { search: '?x=1&view=easy', stored: 'standard' },
  ];

  it.each(cases)('주소 "$search" · 저장 "$stored"', ({ search, stored }) => {
    sessionStorage.clear();
    if (stored !== null) sessionStorage.setItem('view', stored);
    window.history.replaceState(null, '', `/${search}`);
    document.documentElement.removeAttribute('data-view');

    new Function(script)();

    expect(document.documentElement.dataset.view).toBe(resolveViewMode(search, fakeStorage(stored)));
    // 결정한 값을 세션에도 남긴다.
    expect(sessionStorage.getItem('view')).toBe(document.documentElement.dataset.view);
  });
});
