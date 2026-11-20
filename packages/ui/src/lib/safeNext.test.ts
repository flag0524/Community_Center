// 로그인 뒤 돌아갈 주소가 앱 안 경로로만 제한되는지(열린 리다이렉트 방지) 확인하는 시험
import { describe, expect, it } from 'vitest';
import { safeNext } from './safeNext';

describe('safeNext', () => {
  it('앱 안 경로는 그대로 돌려준다', () => {
    expect(safeNext('/me/applications')).toBe('/me/applications');
    expect(safeNext('/courses?status=OPEN')).toBe('/courses?status=OPEN');
  });

  it('없거나 경로가 아니면 첫 화면으로 보낸다', () => {
    expect(safeNext(null)).toBe('/');
    expect(safeNext('')).toBe('/');
    expect(safeNext('me/applications')).toBe('/');
  });

  it('다른 사이트를 가리키는 주소는 거절한다', () => {
    expect(safeNext('//evil.example')).toBe('/');
    expect(safeNext('https://evil.example/')).toBe('/');
    expect(safeNext('/\\evil.example')).toBe('/');
  });

  it('제어문자가 든 주소는 거절한다', () => {
    expect(safeNext('/ok\nSet-Cookie: x=1')).toBe('/');
    expect(safeNext('/ok\u0000')).toBe('/');
  });

  it('로그인 화면으로 되돌아가 반복되지 않게 첫 화면으로 보낸다', () => {
    expect(safeNext('/login')).toBe('/');
    expect(safeNext('/login?next=%2F')).toBe('/');
    expect(safeNext('/loginx')).toBe('/loginx');
  });
});