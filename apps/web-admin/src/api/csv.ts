// 서버가 만든 CSV를 받아 파일로 저장하는 내려받기 도우미. 오류 응답은 ApiRequestError로 바꾼다
import type { ErrorResponse } from '@jori/api-client';
import { ApiRequestError } from './http';

const API_BASE = '/api/admin/v1';

// 브라우저 저장 동작은 시험에서 바꿔 끼울 수 있게 따로 둔다
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function filenameOf(disposition: string | null, fallback: string): string {
  return /filename="([^"]+)"/.exec(disposition ?? '')?.[1] ?? fallback;
}

export async function downloadCsv(path: string, query: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}${query}`, { credentials: 'include', headers: { Accept: 'text/csv' } });
  if (!response.ok) {
    const text = await response.text();
    let body: ErrorResponse | null;
    try {
      body = JSON.parse(text) as ErrorResponse;
    } catch {
      body = null;
    }
    throw new ApiRequestError(response.status, body);
  }
  saveBlob(await response.blob(), filenameOf(response.headers.get('Content-Disposition'), 'export.csv'));
}