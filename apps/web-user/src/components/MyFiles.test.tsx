// 회원 첨부(지원서·문의에 저장 뒤 파일 추가, 서버가 알려 준 한도, 검사 대기·정상·차단 표시, 개수·형식·크기 거절, 제거, 내려받기, 자기 파일만)를 확인하는 시험
import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { createInstructorApplication } from '../api/instructors';
import { ApiRequestError } from '../api/http';
import { setMockNow } from '../mocks/clock';
import { renderApp, server, signInAsDemo, useMockServer } from '../test/render';

// jsdom의 FormData는 Node의 fetch로 보낼 수 없어 올리기만 모의 서버의 검사 규칙으로 바로 연결한다. 실제 multipart 전송은 브라우저 시험이 확인한다.
const sentKeys = vi.hoisted(() => [] as string[]);
vi.mock('../api/myFiles', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/myFiles')>();
  const { receiveUpload } = await import('../mocks/files');
  const { currentMockMember } = await import('../mocks/auth');
  return {
    ...original,
    uploadMyFile: async (ownerPath: string, file: File, key: string) => {
      sentKeys.push(key);
      const result = receiveUpload(ownerPath, currentMockMember()!.memberId, { name: file.name, size: file.size });
      if ('file' in result) return result.file;
      throw new ApiRequestError(result.status, { code: result.code, message: '요청을 처리하지 못했습니다.', fields: result.fields ?? {}, requestId: 'test' });
    },
  };
});

useMockServer();

const DURING = new Date('2026-09-08T10:00:00+09:00'); // 모의 모집공고(요가)가 모집중인 때
const pdf = (name = '자격증.pdf', size = 1024) => {
  const file = new File(['x'], name, { type: 'application/pdf' });
  Object.defineProperty(file, 'size', { value: size });
  return file;
};
const chooser = () => screen.findByLabelText('파일 추가');
const list = async (label: string) => within(await screen.findByRole('list', { name: label })).getAllByRole('listitem');

async function createApplication(): Promise<string> {
  setMockNow(DURING);
  const created = await createInstructorApplication({ recruitmentId: '2', categoryId: '1', desiredCourse: '요가 심화반', career: '경력 5년' }, `key-${Math.random()}`);
  return created.applicationId;
}

describe('문의 첨부', () => {
  it('새 문의는 등록한 뒤에 파일을 추가하라고 안내하고 파일 선택이 없다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/write');
    expect(await screen.findByText('첨부 파일은 문의를 등록한 뒤 수정 화면에서 추가할 수 있습니다.')).toBeInTheDocument();
    expect(screen.queryByLabelText('파일 추가')).not.toBeInTheDocument();
  });

  it('답변 전 문의는 서버가 알려 준 한도와 함께 비어 있는 첨부 영역을 보인다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/602/edit');
    expect(await screen.findByText('올린 파일이 없습니다.')).toBeInTheDocument();
    expect(screen.getByText(/10개까지, 한 개당 20.0MB 이하, pdf · hwp · hwpx · docx · xlsx · jpg · png 파일을 올릴 수 있습니다/)).toBeInTheDocument();
  });

  it('올린 직후에는 검사 중이라 내려받을 수 없고 검사가 끝나면 내려받기 링크가 생긴다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/602/edit');
    await userEvent.upload(await chooser(), pdf('영수증.pdf', 2048));
    const [row] = await list('첨부 파일 목록');
    expect(row).toHaveTextContent('2KB · 검사 중');
    expect(within(row!).queryByRole('link')).not.toBeInTheDocument();
    const link = await screen.findByRole('link', { name: '영수증.pdf' }, { timeout: 8000 });
    expect(link).toHaveAttribute('href', expect.stringMatching(/^\/api\/v1\/me\/files\/32\d+$/));
    expect(screen.getByText(/정상/)).toBeInTheDocument();
  }, 15_000);

  it('답변이 달린 문의는 첨부가 잠겨 있다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/601/edit');
    expect(await screen.findByText('지금은 파일을 추가하거나 제거할 수 없습니다.')).toBeInTheDocument();
    expect(screen.queryByLabelText('파일 추가')).not.toBeInTheDocument();
  });

  it('남의 문의 첨부는 열 수 없다', async () => {
    await signInAsDemo();
    expect((await fetch('/api/v1/me/inquiries/603/files')).status).toBe(404);
  });
});

describe('파일 올리기 거절', () => {
  it('허용하지 않는 형식·빈 파일·큰 파일은 올리기 전에 파일별로 이유를 보이고 서버로 보내지 않는다', async () => {
    sentKeys.length = 0;
    await signInAsDemo();
    renderApp('/board/qna/602/edit');
    await userEvent.upload(await chooser(), [new File(['x'], '실행.exe'), pdf('빈.pdf', 0), pdf('큰.pdf', 21 * 1024 * 1024)], { applyAccept: false });
    const alert = await screen.findByRole('alert');
    expect(within(alert).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      '실행.exe: 허용되지 않는 형식입니다. (pdf, hwp, hwpx, docx, xlsx, jpg, png)',
      '빈.pdf: 빈 파일은 올릴 수 없습니다.',
      '큰.pdf: 파일은 20.0MB 이하만 올릴 수 있습니다.',
    ]);
    expect(sentKeys).toHaveLength(0);
  });

  it('소유 업무당 10개를 넘으면 서버가 거절하고 파일 이름이 128자를 넘어도 거절한다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/602/edit');
    await userEvent.upload(await chooser(), Array.from({ length: 11 }, (_, index) => pdf(`문서${index + 1}.pdf`)));
    expect(await screen.findByText('문서11.pdf: 파일은 10개까지 올릴 수 있습니다.')).toBeInTheDocument();
    expect(await list('첨부 파일 목록')).toHaveLength(10);
  });

  it('파일마다 서로 다른 멱등키로 올린다', async () => {
    sentKeys.length = 0;
    await signInAsDemo();
    renderApp('/board/qna/602/edit');
    await userEvent.upload(await chooser(), [pdf('하나.pdf'), pdf('둘.pdf')]);
    await list('첨부 파일 목록');
    expect(sentKeys).toHaveLength(2);
    expect(new Set(sentKeys).size).toBe(2);
    expect(sentKeys.every((key) => key.length >= 8)).toBe(true);
  });
});

describe('잠금과 소유', () => {
  it('고칠 수 없는 문의는 올린 파일을 보이되 제거 버튼이 없다', async () => {
    server.use(http.get('/api/v1/me/inquiries/601/files', () => HttpResponse.json({ items: [{ fileId: '3200000000000000000007', fileName: '확정.pdf', sizeBytes: 1024, status: 'SAFE', registeredOn: '2026-11-08', blockReason: null }], canEdit: false, maxFiles: 10, maxBytes: 20971520, allowedExtensions: ['pdf'] })));
    await signInAsDemo();
    renderApp('/board/qna/601/edit');
    expect(await screen.findByRole('link', { name: '확정.pdf' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^제거/ })).not.toBeInTheDocument();
  });

  it('서버는 답변이 달린 문의나 남의 문의에는 올리기를 거절한다', async () => {
    const { receiveUpload } = await import('../mocks/files');
    const demo = '1000000000000000000001';
    expect(receiveUpload('/me/inquiries/601', demo, { name: 'a.pdf', size: 10 })).toMatchObject({ status: 409, code: 'CONFLICT_STATE' });
    expect(receiveUpload('/me/inquiries/603', demo, { name: 'a.pdf', size: 10 })).toMatchObject({ status: 404, code: 'NOT_FOUND' });
  });

  it('파일 이름이 128자를 넘으면 서버가 거절한다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/602/edit');
    const name = `${'가'.repeat(129)}.pdf`;
    await userEvent.upload(await chooser(), pdf(name));
    expect(await screen.findByText(`${name}: 파일 이름은 128자를 넘을 수 없습니다.`)).toBeInTheDocument();
  });
});

describe('제거와 내려받기', () => {
  it('두 번 확인해 제거하면 목록에서 사라진다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/602/edit');
    await userEvent.upload(await chooser(), pdf('지울 것.pdf'));
    await userEvent.click(await screen.findByRole('button', { name: '제거 (지울 것.pdf)' }));
    await userEvent.click(screen.getByRole('button', { name: '삭제하기' }));
    expect(await screen.findByText('올린 파일이 없습니다.')).toBeInTheDocument();
  });

  it('제거가 거절되면 사유를 보인다', async () => {
    server.use(http.delete('/api/v1/me/files/:id', () => HttpResponse.json({ code: 'CONFLICT_STATE', message: '지금은 처리할 수 없습니다.', requestId: 'r' }, { status: 409 })));
    await signInAsDemo();
    renderApp('/board/qna/602/edit');
    await userEvent.upload(await chooser(), pdf('지울 것.pdf'));
    await userEvent.click(await screen.findByRole('button', { name: '제거 (지울 것.pdf)' }));
    await userEvent.click(screen.getByRole('button', { name: '삭제하기' }));
    expect(await screen.findByText('지금은 처리할 수 없습니다.')).toBeInTheDocument();
  });

  it('검사를 통과한 내 파일만 첨부 파일로 내려받고 검사 대기·남의 파일은 404다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/602/edit');
    await userEvent.upload(await chooser(), pdf('받기.pdf'));
    const link = await screen.findByRole('link', { name: '받기.pdf' }, { timeout: 8000 });
    const response = await fetch(link.getAttribute('href')!);
    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Disposition')).toContain("attachment; filename*=UTF-8''");
    expect(response.headers.get('X-Content-Type-Options')).toBe('nosniff');
    expect(response.headers.get('Cache-Control')).toBe('private, no-store');
    expect((await fetch('/api/v1/me/files/3200000000000000000099')).status).toBe(404);
  }, 15_000);

  it('악성코드가 의심되는 파일은 차단되어 사유만 보인다', async () => {
    await signInAsDemo();
    renderApp('/board/qna/602/edit');
    await userEvent.upload(await chooser(), pdf('virus.pdf'));
    expect(await screen.findByText(/차단 · 악성코드가 의심됩니다\./, undefined, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'virus.pdf' })).not.toBeInTheDocument();
  }, 15_000);
});

describe('강사 지원서 증빙', () => {
  it('신청한 뒤 수정 화면에서 증빙을 올릴 수 있다', async () => {
    await signInAsDemo();
    const id = await createApplication();
    renderApp(`/me/instructor-applications/${id}/edit`);
    expect(await screen.findByRole('heading', { name: '증빙 파일' })).toBeInTheDocument();
    await userEvent.upload(await chooser(), pdf('경력증명서.pdf'));
    expect((await list('증빙 파일 목록'))[0]).toHaveTextContent('경력증명서.pdf');
  });

  it('새 지원서는 신청한 뒤에 증빙을 추가하라고 안내한다', async () => {
    setMockNow(DURING);
    await signInAsDemo();
    renderApp('/instructors/recruit/2/apply');
    expect(await screen.findByText('증빙 파일은 지원서를 신청한 뒤 수정 화면에서 추가할 수 있습니다.')).toBeInTheDocument();
  });

  it('심사가 진행되어 고칠 수 없는 지원서는 증빙이 잠긴다', async () => {
    await signInAsDemo();
    const id = await createApplication();
    server.use(http.get(`/api/v1/me/instructor-applications/${id}/files`, () => HttpResponse.json({ items: [], canEdit: false, maxFiles: 10, maxBytes: 20971520, allowedExtensions: ['pdf'] })));
    renderApp(`/me/instructor-applications/${id}/edit`);
    expect(await screen.findByText('지금은 파일을 추가하거나 제거할 수 없습니다.')).toBeInTheDocument();
  });

  it('남의 지원서 증빙은 열 수 없다', async () => {
    await signInAsDemo();
    expect((await fetch('/api/v1/me/instructor-applications/9999/files')).status).toBe(404);
  });
});

describe('올리기 요청의 모양', () => {
  it('파일을 multipart의 file 칸으로 한 개 보내고 멱등키와 보호 토큰을 싣되 내용 형식은 직접 적지 않는다', async () => {
    const { uploadMyFile } = await vi.importActual<typeof import('../api/myFiles')>('../api/myFiles');
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return Response.json(url.endsWith('/auth/session') ? { csrfToken: 'token-1' } : { fileId: '1', fileName: 'a.pdf', sizeBytes: 1, status: 'PENDING', registeredOn: '2026-11-08', blockReason: null });
    });
    try {
      await act(async () => {
        await uploadMyFile('/me/inquiries/602', new File(['abc'], 'a.pdf', { type: 'application/pdf' }), 'key-1');
      });
      const upload = calls.find((call) => call.url.endsWith('/me/inquiries/602/files'))!;
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