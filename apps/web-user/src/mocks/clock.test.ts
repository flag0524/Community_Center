// 모의 서버 시계가 주소의 mockNow를 세션에 기억하고 잘못된 값은 무시하는지 확인하는 시험
import { afterEach, describe, expect, it } from 'vitest';
import { initMockClockFromLocation, mockNow, setMockNow } from './clock';

afterEach(() => {
  setMockNow(null);
  sessionStorage.clear();
  window.history.replaceState(null, '', '/');
});

const at = (search: string) => window.history.replaceState(null, '', `/${search}`);

describe('모의 시계', () => {
  it('아무것도 정하지 않으면 실제 현재 시각을 쓴다', () => {
    const before = Date.now();
    const value = mockNow().getTime();
    expect(value).toBeGreaterThanOrEqual(before);
    expect(value).toBeLessThanOrEqual(Date.now());
  });

  it('시험이 고정한 시각을 쓰고 해제하면 돌아온다', () => {
    setMockNow(new Date('2026-09-08T10:00:00+09:00'));
    expect(mockNow().toISOString()).toBe('2026-09-08T01:00:00.000Z');
    setMockNow(null);
    expect(mockNow().getFullYear()).toBeGreaterThanOrEqual(2026);
  });

  it('고정한 시각을 돌려줄 때마다 새 객체라 호출한 쪽이 바꿔도 영향이 없다', () => {
    setMockNow(new Date('2026-09-08T10:00:00+09:00'));
    mockNow().setFullYear(1999);
    expect(mockNow().getFullYear()).toBe(2026);
  });

  it('주소의 날짜는 그날 한국시간 정오로 보고 세션에 기억한다', () => {
    at('?mockNow=2026-09-08');
    initMockClockFromLocation();
    expect(sessionStorage.getItem('mockNow')).toBe('2026-09-08');
    expect(mockNow().toISOString()).toBe('2026-09-08T03:00:00.000Z');

    // 주소에서 값이 사라져도 세션에 남아 있어 화면을 옮겨도 유지된다.
    at('');
    expect(mockNow().toISOString()).toBe('2026-09-08T03:00:00.000Z');
  });

  it('시각까지 적으면 그 시각을 그대로 쓴다', () => {
    at('?mockNow=2026-08-20T10:00:00%2B09:00');
    initMockClockFromLocation();
    expect(mockNow().toISOString()).toBe('2026-08-20T01:00:00.000Z');
  });

  it('잘못된 값은 무시하고 기억하지 않는다', () => {
    at('?mockNow=어제');
    initMockClockFromLocation();
    expect(sessionStorage.getItem('mockNow')).toBeNull();
    expect(mockNow().getFullYear()).toBeGreaterThanOrEqual(2026);
  });

  it('값을 비우면 기억해 둔 시각을 해제한다', () => {
    sessionStorage.setItem('mockNow', '2026-09-08');
    at('?mockNow=');
    initMockClockFromLocation();
    expect(sessionStorage.getItem('mockNow')).toBeNull();
  });

  it('주소에 mockNow가 없으면 기억해 둔 값을 건드리지 않는다', () => {
    sessionStorage.setItem('mockNow', '2026-09-08');
    at('?page=2');
    initMockClockFromLocation();
    expect(sessionStorage.getItem('mockNow')).toBe('2026-09-08');
  });
});
