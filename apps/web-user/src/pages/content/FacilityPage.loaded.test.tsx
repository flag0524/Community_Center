// 일부 시설의 사진 파일이 있을 때 시설안내 표가 사진과 준비 중 표시를 층에 맞게 보이는지 확인하는 시험
import { screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderApp, useMockServer } from '../../test/render';

useMockServer();

const asked: string[] = [];
const photo = (name: string) => `/dev-assets/facility/${encodeURIComponent(name)}.jpg`;

beforeEach(() => {
  const found = new Set([photo('문화공연장'), photo('통합민원실')]);
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
});
afterEach(() => vi.unstubAllGlobals());

describe('시설안내의 사진', () => {
  it('사진이 있는 층에는 그 시설의 사진을, 없는 층에는 준비 중을 보인다', async () => {
    renderApp('/center/facility');
    const first = await screen.findByRole('img', { name: '문화공연장 사진' });
    const table = screen.getByRole('table', { name: '조리읍 행정복지센터 표' });
    expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['층', '시설', '사진']);
    const rows = within(table).getAllByRole('row').slice(1);
    expect(within(rows[0]!).getByRole('img', { name: '문화공연장 사진' })).toBe(first);
    expect(first).toHaveAttribute('src', photo('문화공연장'));
    expect(within(rows[1]!).getByRole('img', { name: '통합민원실 사진' })).toHaveAttribute('src', photo('통합민원실'));
    for (const row of rows.slice(2)) {
      expect(within(row).getByText('사진 준비 중')).toBeInTheDocument();
      expect(within(row).queryByRole('img')).not.toBeInTheDocument();
    }
  });
});
