// 소유 업무 첨부(업무 저장 뒤 파일 추가, 서버가 알려 준 한도, 검사 대기·정상·차단 표시, 개수·형식·크기 거절, 제거, 내려받기 헤더)를 확인하는 시험
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { ApiRequestError } from '../api/http';
import { apiError } from '../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../test/render';
import { OwnerFiles } from './OwnerFiles';

// jsdom의 FormData는 Node의 fetch로 보낼 수 없어 올리기만 모의 서버의 검사 규칙으로 바로 연결한다. 실제 multipart 전송은 브라우저 시험이 확인한다.
const sentKeys = vi.hoisted(() => [] as string[]);
vi.mock('../api/ownerFiles', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/ownerFiles')>();
  const { receiveUpload } = await import('../mocks/files');
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

const POST = `17${'1'.padStart(20, '0')}`;
const COURSE = `4${'1'.padStart(21, '0')}`;
const pdf = (name = '공고.pdf', size = 1024) => {
  const file = new File(['x'], name, { type: 'application/pdf' });
  Object.defineProperty(file, 'size', { value: size });
  return file;
};
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);
const chooser = () => screen.findByLabelText('파일 추가');
const renderFiles = (pollMs = 30) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <OwnerFiles ownerPath={`/posts/${POST}`} label="첨부파일" pollMs={pollMs} />
    </QueryClientProvider>,
  );

describe('게시물·강좌 양식의 첨부 영역', () => {
  it('새 게시물은 저장한 뒤에 파일을 추가하라고 안내하고 파일 선택이 없다', async () => {
    await signInAs('group');
    renderApp('/mbr/posts/new');
    expect(await screen.findByText('파일은 게시물을 저장한 뒤에 추가할 수 있습니다.')).toBeInTheDocument();
    expect(screen.queryByLabelText('파일 추가')).not.toBeInTheDocument();
  });

  it('저장된 게시물은 서버가 알려 준 한도와 함께 비어 있는 첨부 영역을 보인다', async () => {
    await signInAs('group');
    renderApp(`/mbr/posts/${POST}`);
    expect(await screen.findByText('올린 파일이 없습니다.')).toBeInTheDocument();
    expect(screen.getByText(/10개까지, 한 개당 20.0MB 이하, pdf · hwp · hwpx · docx · xlsx · jpg · png 파일을 올릴 수 있습니다/)).toBeInTheDocument();
  });

  it('강좌는 강의계획서 영역을 보이고 올린 파일이 목록에 쌓인다', async () => {
    await signInAs('group');
    renderApp(`/edu/courses/${COURSE}`);
    await screen.findByRole('heading', { name: '강의계획서' });
    await userEvent.upload(await chooser(), pdf('요가 계획서.pdf', 2048));
    expect((await rows('강의계획서 목록')).map((row) => cells(row).slice(0, 3))).toEqual([['요가 계획서.pdf', '2KB', '검사 대기']]);
  });
});

describe('파일 올리기와 검사 상태', () => {
  it('올린 직후에는 검사 대기라 내려받을 수 없고 검사가 끝나면 내려받기 링크가 생긴다', async () => {
    await signInAs('group');
    renderFiles();
    await userEvent.upload(await chooser(), pdf());
    expect(await screen.findByText('검사 대기')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '공고.pdf' })).not.toBeInTheDocument();
    const link = await screen.findByRole('link', { name: '공고.pdf' });
    expect(link).toHaveAttribute('href', expect.stringMatching(/^\/api\/admin\/v1\/files\/31\d+\/download$/));
    expect(screen.getByText('정상')).toBeInTheDocument();
  });

  it('악성코드가 의심되는 파일은 차단되어 사유만 보이고 내려받을 수 없다', async () => {
    await signInAs('group');
    renderFiles();
    await userEvent.upload(await chooser(), pdf('virus.pdf'));
    expect(await screen.findByText('차단 · 악성코드가 의심됩니다.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'virus.pdf' })).not.toBeInTheDocument();
  });

  it('허용하지 않는 형식·빈 파일·큰 파일은 올리기 전에 파일별로 이유를 보인다', async () => {
    sentKeys.length = 0;
    await signInAs('group');
    renderFiles();
    await userEvent.upload(await chooser(), [new File(['x'], '실행.exe'), pdf('빈.pdf', 0), pdf('큰.pdf', 21 * 1024 * 1024)], { applyAccept: false });
    const alert = await screen.findByRole('alert');
    expect(within(alert).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      '실행.exe: 허용되지 않는 형식입니다. (pdf, hwp, hwpx, docx, xlsx, jpg, png)',
      '빈.pdf: 빈 파일은 올릴 수 없습니다.',
      '큰.pdf: 파일은 20.0MB 이하만 올릴 수 있습니다.',
    ]);
    expect(screen.getByText('올린 파일이 없습니다.')).toBeInTheDocument();
    expect(sentKeys).toHaveLength(0); // 서버로 보내지 않고 화면에서 먼저 걸렀다
  });

  it('소유 업무당 10개를 넘으면 서버가 거절하고 올라간 파일은 그대로 남는다', async () => {
    await signInAs('group');
    renderFiles(60_000);
    await userEvent.upload(await chooser(), Array.from({ length: 11 }, (_, index) => pdf(`문서${index + 1}.pdf`)));
    expect(await screen.findByText('문서11.pdf: 파일은 10개까지 올릴 수 있습니다.')).toBeInTheDocument();
    expect(await rows('첨부파일 목록')).toHaveLength(10);
  });

  it('파일마다 서로 다른 멱등키로 올린다', async () => {
    sentKeys.length = 0;
    await signInAs('group');
    renderFiles(60_000);
    await userEvent.upload(await chooser(), [pdf('하나.pdf'), pdf('둘.pdf')]);
    await rows('첨부파일 목록');
    expect(sentKeys).toHaveLength(2);
    expect(sentKeys.every((key) => key.length >= 8)).toBe(true);
    expect(new Set(sentKeys).size).toBe(2);
  });

  it('파일 이름이 128자를 넘으면 서버가 거절한다', async () => {
    await signInAs('group');
    renderFiles();
    const name = `${'가'.repeat(129)}.pdf`;
    await userEvent.upload(await chooser(), pdf(name));
    expect(await screen.findByText(`${name}: 파일 이름은 128자를 넘을 수 없습니다.`)).toBeInTheDocument();
  });
});

describe('제거와 잠금, 내려받기', () => {
  it('두 번 확인해 제거하면 목록에서 사라진다', async () => {
    await signInAs('group');
    renderFiles(60_000);
    await userEvent.upload(await chooser(), pdf());
    await userEvent.click(await screen.findByRole('button', { name: '제거 (공고.pdf)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 제거 (공고.pdf)' }));
    expect(await screen.findByText('올린 파일이 없습니다.')).toBeInTheDocument();
  });

  it('서버가 잠겼다고 알리면 추가·제거를 막고 안내한다', async () => {
    server.use(http.get(`/api/admin/v1/posts/:id/files`, () => Response.json({ items: [{ fileId: `31${'7'.padStart(20, '0')}`, fileName: '확정.pdf', sizeBytes: 1024, status: 'SAFE', registeredOn: '2026-11-07', blockReason: null }], canEdit: false, maxFiles: 10, maxBytes: 20971520, allowedExtensions: ['pdf'] })));
    await signInAs('group');
    renderFiles();
    expect(await screen.findByText('지금은 파일을 추가하거나 제거할 수 없습니다.')).toBeInTheDocument();
    expect(screen.queryByLabelText('파일 추가')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^제거/ })).not.toBeInTheDocument();
  });

  it('제거 요청이 거절되면 사유를 보인다', async () => {
    server.use(http.delete('/api/admin/v1/files/:id', () => apiError('CONFLICT_STATE')));
    await signInAs('group');
    renderFiles(60_000);
    await userEvent.upload(await chooser(), pdf());
    await userEvent.click(await screen.findByRole('button', { name: '제거 (공고.pdf)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 제거 (공고.pdf)' }));
    expect(await screen.findByText('현재 상태에서는 처리할 수 없습니다.')).toBeInTheDocument();
  });

  it('검사를 통과한 파일은 첨부 파일로 내려받고 검사 대기 파일은 404이며 관리자 내려받기가 기록된다', async () => {
    await signInAs('group');
    renderFiles();
    await userEvent.upload(await chooser(), pdf('받기.pdf'));
    await screen.findByText('검사 대기');
    const link = await screen.findByRole('link', { name: '받기.pdf' });
    const href = link.getAttribute('href')!;
    const response = await fetch(href);
    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Disposition')).toContain("attachment; filename*=UTF-8''");
    expect(response.headers.get('X-Content-Type-Options')).toBe('nosniff');
    expect(response.headers.get('Cache-Control')).toBe('private, no-store');
    const detail = (await (await fetch(href.replace('/download', ''))).json()) as { downloads: Array<{ by: string; byAdmin: boolean }> };
    expect(detail.downloads).toEqual([expect.objectContaining({ by: '김관리', byAdmin: true })]);
    expect((await fetch(`/api/admin/v1/files/31${'5'.padStart(20, '0')}/download`)).status).toBe(404);
  });
});

describe('올리기 요청의 모양', () => {
  it('파일을 multipart의 file 칸으로 한 개 보내고 멱등키와 보호 토큰을 싣되 내용 형식은 직접 적지 않는다', async () => {
    const { uploadOwnerFile } = await vi.importActual<typeof import('../api/ownerFiles')>('../api/ownerFiles');
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return Response.json(url.endsWith('/auth/session') ? { csrfToken: 'token-1' } : { fileId: '1', fileName: 'a.pdf', sizeBytes: 1, status: 'PENDING', registeredOn: '2026-11-07', blockReason: null });
    });
    try {
      const file = new File(['abc'], 'a.pdf', { type: 'application/pdf' });
      await uploadOwnerFile('/posts/17', file, 'key-1');
      const upload = calls.find((call) => call.url.endsWith('/posts/17/files'))!;
      const headers = upload.init?.headers as Record<string, string>;
      expect(upload.init?.method).toBe('POST');
      expect(headers['Idempotency-Key']).toBe('key-1');
      expect(headers['X-CSRF-Token']).toBe('token-1');
      expect(headers['Content-Type']).toBeUndefined();
      const form = upload.init?.body as FormData;
      expect(form.getAll('file')).toHaveLength(1);
      expect((form.get('file') as File).name).toBe('a.pdf');
    } finally {
      vi.unstubAllGlobals();
    }
  });
});