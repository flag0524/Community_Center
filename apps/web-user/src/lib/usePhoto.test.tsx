// 사진 확인 훅이 불러오기 성공·실패·중복 확인 없음을 제대로 구분하는지 확인하는 시험
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { usePhoto } from './usePhoto';

const created: string[] = [];

function stubImage(outcome: 'load' | 'error') {
  class FakeImage {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    set src(value: string) {
      created.push(value);
      queueMicrotask(() => (outcome === 'load' ? this.onload : this.onerror)?.());
    }
  }
  vi.stubGlobal('Image', FakeImage);
}

afterEach(() => {
  vi.unstubAllGlobals();
  created.length = 0;
});

describe('usePhoto', () => {
  it('처음에는 확인 중이고 사진이 있으면 ok가 된다', async () => {
    stubImage('load');
    const { result } = renderHook(() => usePhoto('/photo-exists.jpg'));
    expect(result.current).toBe('loading');
    await waitFor(() => expect(result.current).toBe('ok'));
  });

  it('사진이 없으면 failed가 된다', async () => {
    stubImage('error');
    const { result } = renderHook(() => usePhoto('/photo-missing.jpg'));
    expect(result.current).toBe('loading');
    await waitFor(() => expect(result.current).toBe('failed'));
  });

  it('같은 사진을 여러 곳에서 물어도 한 번만 확인한다', async () => {
    stubImage('load');
    const first = renderHook(() => usePhoto('/photo-shared.jpg'));
    const second = renderHook(() => usePhoto('/photo-shared.jpg'));
    await waitFor(() => expect(first.result.current).toBe('ok'));
    await waitFor(() => expect(second.result.current).toBe('ok'));
    expect(created.filter((src) => src === '/photo-shared.jpg')).toHaveLength(1);
  });
});
