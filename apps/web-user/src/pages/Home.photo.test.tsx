// 청사 사진이 있을 때와 없을 때 홈 히어로·쉬운 화면·갤러리가 어떻게 달라지는지 확인하는 시험
import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderApp, useMockServer } from '../test/render';

let status: 'loading' | 'ok' | 'failed' = 'loading';
vi.mock('../lib/usePhoto', () => ({
  BUILDING_PHOTO: '/dev-assets/building.jpg',
  usePhoto: () => status,
}));

useMockServer();
beforeEach(() => {
  status = 'loading';
});

async function renderHome() {
  renderApp('/');
  await screen.findByLabelText('분야별 강좌안내');
}

describe('청사 사진', () => {
  it('사진이 있으면 히어로·쉬운 화면·갤러리에 그리고 출처를 표시한다', async () => {
    status = 'ok';
    await renderHome();

    expect(document.querySelector('.hero > img')).not.toBeNull();
    expect(document.querySelector('.easy-place figure img')).not.toBeNull();
    expect(document.querySelector('.photo-panel img')).not.toBeNull();
    expect(screen.getByText(/파주시 제공\(2022\.10\.05\)/)).toBeInTheDocument();
  });

  it.each(['failed', 'loading'] as const)('사진이 %s 상태면 이미지와 출처 표기를 그리지 않는다', async (value) => {
    status = value;
    await renderHome();

    expect(document.querySelector('.hero > img')).toBeNull();
    expect(document.querySelector('.easy-place figure')).toBeNull();
    expect(document.querySelector('.photo-panel img')).toBeNull();
    expect(document.querySelector('.photo-credit')).toBeNull();
    // 사진이 없어도 제목과 행동 유도 링크는 그대로 있다.
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /강좌 둘러보기/ })).toBeInTheDocument();
  });
});
