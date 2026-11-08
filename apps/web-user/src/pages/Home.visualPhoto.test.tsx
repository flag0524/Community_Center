// 홈 비주얼이 있으면 서버가 준 사진만 쓰고 청사 사진과 출처를 겹쳐 그리지 않으며, 없으면 청사 사진과 출처를 그리는지 확인하는 시험
import { screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setMockHomeContent } from '../mocks/homeContent';
import { renderApp, useMockServer } from '../test/render';

vi.mock('../lib/usePhoto', () => ({ BUILDING_PHOTO: '/dev-assets/building.jpg', usePhoto: () => 'ok' }));

useMockServer();

afterEach(() => setMockHomeContent(null));

describe('청사 사진과 비주얼', () => {
  it('비주얼이 있으면 서버 사진만 그리고 청사 사진 출처를 붙이지 않는다', async () => {
    setMockHomeContent('full');
    renderApp('/');
    // 홈 응답이 오기 전에는 청사 사진이 먼저 그려지므로 서버 사진으로 바뀔 때까지 기다린다.
    await waitFor(() => expect(screen.getByRole('img', { name: '조리읍 행정복지센터 청사' })).toHaveAttribute('src', '/api/v1/files/9100000000000000000501'));
    expect(document.querySelector('.hero img[src="/dev-assets/building.jpg"]')).toBeNull();
    expect(screen.queryByText(/파주시 제공/)).not.toBeInTheDocument();
  });

  it('비주얼이 없으면 청사 사진과 출처를 그린다', async () => {
    renderApp('/');
    expect(await screen.findByText(/파주시 제공/)).toBeInTheDocument();
    expect(document.querySelector('.hero img[src="/dev-assets/building.jpg"]')).not.toBeNull();
  });
});