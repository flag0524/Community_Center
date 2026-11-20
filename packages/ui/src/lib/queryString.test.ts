// 쿼리 문자열 만들기가 빈 값을 건너뛰고 한글을 안전하게 인코딩하는지 확인하는 시험
import { describe, expect, it } from 'vitest';
import { toQueryString } from './queryString';

describe('toQueryString', () => {
  it('값이 있는 조건만 남긴다', () => {
    expect(toQueryString({ q: '요가', categoryId: '3', day: undefined, status: null, page: 2 })).toBe(
      '?q=%EC%9A%94%EA%B0%80&categoryId=3&page=2',
    );
  });

  it('모두 비어 있으면 빈 문자열이다', () => {
    expect(toQueryString({ q: '', day: undefined })).toBe('');
  });

  it('0도 값으로 본다', () => {
    expect(toQueryString({ page: 0 })).toBe('?page=0');
  });

  it('특수문자는 인코딩한다', () => {
    expect(toQueryString({ q: 'a&b=c' })).toBe('?q=a%26b%3Dc');
  });
});
