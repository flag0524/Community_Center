// 시설 사진 영역(올리기 전 미리보기, 올린 사진 보기, 대표 지정, 제거, 형식·장수 거절, 저장 전 안내)을 확인하는 시험
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiRequestError } from '../../api/http';
import { renderApp, signInAs, useMockServer } from '../../test/render';
import { FacilityPhotos } from './FacilityPhotos';

// jsdom의 FormData는 Node의 fetch로 보낼 수 없어 올리기만 모의 서버의 검사 규칙으로 바로 연결한다. 실제 전송은 브라우저 시험이 확인한다.
const sentKeys = vi.hoisted(() => [] as string[]);
vi.mock('../../api/ownerFiles', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/ownerFiles')>();
  const { receiveUpload } = await import('../../mocks/files');
  return {
    ...original,
    uploadOwnerFile: async (ownerPath: string, file: File, key: string) => {
      sentKeys.push(key);
      const result = receiveUpload(ownerPath, { name: file.name, size: file.size });
      if ('file' in result) return result.file;
      throw new ApiRequestError(result.status, { code: result.code, message: '요청을 처리하지 못했습니다.', fields: result.fields ?? {}, requestId: 'test' });
    },
  };
});

useMockServer();

const ROOM = '7000000000000000000002'; // 강의실 1
const photo = (name: string) => new File(['image'], name, { type: 'image/png' });
const renderPhotos = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <FacilityPhotos facilityId={ROOM} name="강의실 1" pollMs={30} />
    </QueryClientProvider>,
  );
const chooser = () => screen.findByLabelText('사진 선택');
const uploaded = () => screen.findByRole('list', { name: '올린 사진' });
const captions = async () => within(await uploaded()).getAllByRole('listitem').map((item) => item.querySelector('figcaption')!.textContent);

async function upload(...names: string[]) {
  await userEvent.upload(await chooser(), names.map(photo));
  await userEvent.click(await screen.findByRole('button', { name: `${names.length}장 올리기` }));
}
const safe = async (count: number) => waitFor(async () => expect(within(await uploaded()).getAllByRole('img')).toHaveLength(count), { timeout: 3000 });

describe('시설 사진', () => {
  it('고른 사진은 올리기 전에 미리 보이고 올리기를 눌러야 보낸다', async () => {
    await signInAs('group');
    renderPhotos();
    expect(await screen.findByText('올린 사진이 없습니다.')).toBeInTheDocument();
    expect(screen.getByText(/5장까지/)).toBeInTheDocument();
    sentKeys.length = 0;
    await userEvent.upload(await chooser(), [photo('무대.png'), photo('객석.jpg')]);
    const preview = await screen.findByRole('list', { name: '올리기 전 미리보기' });
    const images = await within(preview).findAllByRole('img');
    expect(images.map((image) => image.getAttribute('alt'))).toEqual(['고른 사진 무대.png', '고른 사진 객석.jpg']);
    expect(images[0]!.getAttribute('src')).toMatch(/^data:image\/png;base64,/);
    expect(sentKeys).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: '2장 올리기' }));
    await safe(2);
    expect(sentKeys).toHaveLength(2);
    expect(new Set(sentKeys).size).toBe(2);
    expect(screen.queryByRole('list', { name: '올리기 전 미리보기' })).not.toBeInTheDocument();
    expect(await captions()).toEqual(['무대.png대표', '객석.jpg']);
    const first = within(await uploaded()).getByRole('img', { name: '강의실 1 사진 1' });
    expect(first.getAttribute('src')).toMatch(/^\/api\/admin\/v1\/files\/\d+\/download$/);
  });

  it('선택 취소를 누르면 보내지 않고 미리보기를 지운다', async () => {
    await signInAs('group');
    renderPhotos();
    sentKeys.length = 0;
    await userEvent.upload(await chooser(), photo('무대.png'));
    await userEvent.click(await screen.findByRole('button', { name: '선택 취소' }));
    expect(screen.queryByRole('list', { name: '올리기 전 미리보기' })).not.toBeInTheDocument();
    expect(sentKeys).toHaveLength(0);
  });

  it('대표로 지정하면 맨 앞으로 오고 제거하면 사라진다', async () => {
    await signInAs('group');
    renderPhotos();
    await upload('무대.png', '객석.png');
    await safe(2);
    await userEvent.click(screen.getByRole('button', { name: '객석.png 대표로 지정' }));
    await waitFor(async () => expect(await captions()).toEqual(['객석.png대표', '무대.png']));
    expect(screen.queryByRole('button', { name: '객석.png 대표로 지정' })).not.toBeInTheDocument();
    const second = within(await uploaded()).getAllByRole('listitem')[1]!;
    await userEvent.click(within(second).getByRole('button', { name: /제거/ }));
    await userEvent.click(within(second).getByRole('button', { name: /정말 제거/ }));
    await waitFor(async () => expect(await captions()).toEqual(['객석.png대표']));
  });

  it('이미지가 아니거나 다섯 장을 넘는 사진은 고를 때 알리고 담지 않는다', async () => {
    await signInAs('group');
    renderPhotos();
    const input = await chooser();
    await userEvent.upload(input, new File(['x'], '안내.pdf', { type: 'application/pdf' }), { applyAccept: false });
    expect(await screen.findByRole('alert')).toHaveTextContent('안내.pdf: 이미지(jpg, png)만 올릴 수 있습니다.');
    await userEvent.upload(input, ['1.png', '2.png', '3.png', '4.png', '5.png', '6.png'].map(photo));
    expect(await screen.findByRole('alert')).toHaveTextContent('6.png: 사진은 5장까지 올릴 수 있습니다.');
    await userEvent.click(screen.getByRole('button', { name: '5장 올리기' }));
    await safe(5);
    expect(screen.queryByLabelText('사진 선택')).not.toBeInTheDocument();
    expect(screen.getByText('5장을 모두 올렸습니다. 바꾸려면 먼저 제거해 주세요.')).toBeInTheDocument();
  });

  it('수정 화면에는 사진 영역이 있고 새 시설은 저장한 뒤 올리라고 알린다', async () => {
    await signInAs('group');
    renderApp(`/edu/facilities/${ROOM}`);
    expect(await screen.findByRole('heading', { level: 2, name: '시설 사진' })).toBeInTheDocument();
    expect(await chooser()).toHaveAttribute('accept', '.jpg,.png');
  });

  it('새 시설 화면에는 파일 선택이 없다', async () => {
    await signInAs('group');
    renderApp('/edu/facilities/new');
    expect(await screen.findByText('사진은 시설을 저장한 뒤 올릴 수 있습니다.')).toBeInTheDocument();
    expect(screen.queryByLabelText('사진 선택')).not.toBeInTheDocument();
  });
});
