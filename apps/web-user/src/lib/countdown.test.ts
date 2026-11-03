// 결제기한 카운트다운 계산과 표기, 시계 훅을 확인하는 시험
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { formatCountdown, remainingSeconds, useCountdown } from './countdown';

describe('remainingSeconds', () => {
  const deadline = '2026-09-08T10:10:00+09:00';
  const serverNow = '2026-09-08T10:00:00+09:00';

  it('기한에서 서버 시각을 뺀 값이다', () => {
    expect(remainingSeconds(deadline, serverNow, 0)).toBe(600);
  });

  it('응답을 받은 뒤 흐른 시간만큼 줄어든다(기기 시계가 아니라 서버 시각이 기준이다)', () => {
    expect(remainingSeconds(deadline, serverNow, 12_500)).toBe(588);
  });

  it('기한이 지났으면 0이다', () => {
    expect(remainingSeconds(deadline, serverNow, 700_000)).toBe(0);
  });
});

describe('formatCountdown', () => {
  it.each([
    [600, '10:00'],
    [599, '09:59'],
    [65, '01:05'],
    [0, '00:00'],
  ])('%i초는 %s', (seconds, text) => expect(formatCountdown(seconds)).toBe(text));
});

describe('useCountdown', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('1초마다 줄고 0이 되면 한 번만 알린다', () => {
    const onZero = vi.fn();
    const { result } = renderHook(() =>
      useCountdown('2026-09-08T10:00:03+09:00', '2026-09-08T10:00:00+09:00', onZero),
    );
    expect(result.current).toBe(3);

    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toBe(2);
    expect(onZero).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(5000));
    expect(result.current).toBe(0);
    expect(onZero).toHaveBeenCalledTimes(1);
  });

  it('처음부터 기한이 지났으면 바로 0이고 알린다', () => {
    const onZero = vi.fn();
    const { result } = renderHook(() =>
      useCountdown('2026-09-08T09:59:00+09:00', '2026-09-08T10:00:00+09:00', onZero),
    );
    expect(result.current).toBe(0);
    expect(onZero).toHaveBeenCalledTimes(1);
  });
});
