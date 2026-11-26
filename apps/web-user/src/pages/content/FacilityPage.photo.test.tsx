// 시설 사진 파일이 있을 때와 없을 때 시설안내 표의 사진 열이 어떻게 달라지는지 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp, useMockServer } from '../../test/render';

useMockServer();
afterEach(() => vi.unstubAllGlobals());

/** 주어진 시설 이름의 사진만 불러와지는 것처럼 만든다. 읽은 주소를 돌려준다. */
function photosFor(...names: string[]) {
  const asked: string[] = [];
  const found = new Set(names.map((name) => `/dev-assets/facility/${encodeURIComponent(name)}.jpg`));
  vi.stubGlobal(
    'Image',
    class {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(value: string) {
        asked.push(value);
        queueMicrotask(() => (found.has(value) ? this.onload?.() : this.onerror?.()));
      }
    },
  );
  return asked;
}

const table = () => screen.getByRole('table', { name: '조리읍 행정복지센터 표' });
const headers = () => within(table()).getAllByRole('columnheader').map((cell) => cell.textContent);

describe('시설안내의 사진', () => {
  // 사진 확인 결과는 앱이 기억하므로, 사진이 하나도 없는 경우를 먼저 확인한다
  it('사진 파일이 하나도 없으면 층·시설 표 그대로다', async () => {
    const asked = photosFor();
    renderApp('/center/facility');
    await screen.findByRole('table', { name: '조리읍 행정복지센터 표' });
    await waitFor(() => expect(asked.length).toBeGreaterThanOrEqual(4));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(headers()).toEqual(['층', '시설']);
    expect(screen.queryByText('사진 준비 중')).not.toBeInTheDocument();
  });
});
