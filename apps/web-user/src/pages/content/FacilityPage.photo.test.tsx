// 시설안내의 사진(대표 사진과 장수, 눌러 크게 보기의 이전·다음, 사진 없는 시설의 준비 중 표시)을 확인하는 시험
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';
import { facilities } from '../../mocks/fixtures';
import { renderApp, server, useMockServer } from '../../test/render';

useMockServer();

const url = (n: number) => `/api/v1/files/910000000000000000090${n}`;
/** 시설마다 사진 주소를 정해 모의 응답을 바꾼다. 정하지 않은 시설은 사진이 없다. */
const withPhotos = (photos: Record<string, string[]>) =>
  server.use(http.get('/api/v1/site/facilities', () => HttpResponse.json({ items: facilities.items.map((item) => ({ ...item, photoUrls: photos[item.name] ?? [] })) })));
const table = () => screen.findByRole('table', { name: '조리읍 행정복지센터 표' });
const headers = async () => within(await table()).getAllByRole('columnheader').map((cell) => cell.textContent);

describe('시설안내의 사진', () => {
  it('사진이 하나도 없으면 층·시설 표 그대로다', async () => {
    withPhotos({});
    renderApp('/center/facility');
    expect(await headers()).toEqual(['층', '시설']);
    expect(screen.queryByText('사진 준비 중')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /크게 보기/ })).not.toBeInTheDocument();
  });

  it('사진이 있는 시설에는 대표 사진과 장수를, 없는 시설에는 준비 중을 보인다', async () => {
    withPhotos({ 문화공연장: [url(2), url(1)] });
    renderApp('/center/facility');
    expect(await headers()).toEqual(['층', '시설', '사진']);
    const rows = within(await table()).getAllByRole('row').slice(1);
    const open = within(rows[0]!).getByRole('button', { name: '문화공연장 사진 2장 크게 보기' });
    expect(open).toHaveTextContent('사진 2장 크게 보기');
    expect(open.querySelector('img')).toHaveAttribute('src', url(2)); // 첫 번째가 대표 사진이다
    for (const row of rows.slice(1)) expect(within(row).getByText('사진 준비 중')).toBeInTheDocument();
  });

  it('누르면 큰 창에서 이전·다음으로 넘겨 보고 닫는다', async () => {
    withPhotos({ 문화공연장: [url(2), url(1)] });
    renderApp('/center/facility');
    await userEvent.click(await screen.findByRole('button', { name: '문화공연장 사진 2장 크게 보기' }));
    const dialog = screen.getByRole('dialog', { name: '문화공연장 사진' });
    const shown = () => within(dialog).getByRole('img');
    expect(shown()).toHaveAttribute('src', url(2));
    expect(shown()).toHaveAccessibleName('문화공연장 사진 1 / 2');
    expect(within(dialog).getByRole('button', { name: '이전 사진' })).toBeDisabled();
    await userEvent.click(within(dialog).getByRole('button', { name: '다음 사진' }));
    expect(shown()).toHaveAttribute('src', url(1));
    expect(within(dialog).getByRole('status')).toHaveTextContent('2 / 2');
    expect(within(dialog).getByRole('button', { name: '다음 사진' })).toBeDisabled();
    await userEvent.click(within(dialog).getByRole('button', { name: '이전 사진' }));
    expect(shown()).toHaveAttribute('src', url(2));
    await userEvent.click(within(dialog).getByRole('button', { name: '닫기' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('센터 사진은 센터 이름 아래에 보이고 한 장이면 이전·다음 버튼이 없다', async () => {
    withPhotos({ '조리읍 행정복지센터': [url(1)] });
    renderApp('/center/facility');
    await userEvent.click(await screen.findByRole('button', { name: '조리읍 행정복지센터 사진 1장 크게 보기' }));
    const dialog = screen.getByRole('dialog', { name: '조리읍 행정복지센터 사진' });
    expect(within(dialog).queryByRole('button', { name: /이전|다음/ })).not.toBeInTheDocument();
    expect(await headers()).toEqual(['층', '시설']); // 강의실 사진이 없으면 표에는 사진 열이 없다
  });
});
