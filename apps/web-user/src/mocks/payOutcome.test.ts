// 모의 결제 결과 선택(?mockPay=)을 확인하는 시험
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { initMockPayFromLocation, mockPayOutcome, setMockPayOutcome } from './payOutcome';

beforeEach(() => window.sessionStorage.clear());
afterEach(() => {
  setMockPayOutcome(null);
  window.history.replaceState(null, '', '/');
});

describe('mockPayOutcome', () => {
  it('아무것도 고르지 않으면 성공이다', () => {
    expect(mockPayOutcome()).toBe('success');
  });

  it('시험에서 고정한 값을 우선한다', () => {
    setMockPayOutcome('failed');
    expect(mockPayOutcome()).toBe('failed');
  });

  it.each(['success', 'failed', 'unknown', 'expired'] as const)('주소의 ?mockPay=%s 를 세션에 기억한다', (value) => {
    window.history.replaceState(null, '', `/payment/1?mockPay=${value}`);
    initMockPayFromLocation();
    window.history.replaceState(null, '', '/payment/1');
    expect(mockPayOutcome()).toBe(value);
  });

  it('모르는 값은 무시하고 빈 값은 해제한다', () => {
    window.history.replaceState(null, '', '/?mockPay=failed');
    initMockPayFromLocation();
    window.history.replaceState(null, '', '/?mockPay=nonsense');
    initMockPayFromLocation();
    expect(mockPayOutcome()).toBe('failed');

    window.history.replaceState(null, '', '/?mockPay=');
    initMockPayFromLocation();
    expect(mockPayOutcome()).toBe('success');
  });
});
