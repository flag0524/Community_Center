// 생성된 API 타입을 쓰는 fetch 도우미. 오류 응답은 ApiRequestError로 바꿔 던진다
import type { ErrorResponse } from '@jori/api-client';

const API_BASE = '/api/v1';

export class ApiRequestError extends Error {
  readonly status: number;
  readonly body: ErrorResponse | null;

  constructor(status: number, body: ErrorResponse | null) {
    super(body?.message ?? `요청에 실패했습니다 (${status})`);
    this.name = 'ApiRequestError';
    this.status = status;
    this.body = body;
  }
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return typeof value === 'object' && value !== null && 'code' in value && 'requestId' in value;
}

function parseJson(text: string): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
    signal,
  });
  const payload = parseJson(await response.text());
  if (!response.ok) throw new ApiRequestError(response.status, isErrorResponse(payload) ? payload : null);
  return payload as T;
}
