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

// 상태를 바꾸는 요청의 X-CSRF-Token 값. 세션 응답이 올 때마다 바뀔 수 있어 모듈 안에서만 들고 있다.
let csrfToken: string | null = null;

export function rememberCsrfToken(token: string | null | undefined): void {
  csrfToken = token ?? null;
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'include', ...init });
  const payload = parseJson(await response.text());
  if (!response.ok) throw new ApiRequestError(response.status, isErrorResponse(payload) ? payload : null);
  // 세션 응답(조회·로그인)이 새 토큰을 담고 있으면 이후 요청부터 그 값을 쓴다.
  if (typeof payload === 'object' && payload !== null && 'csrfToken' in payload) {
    rememberCsrfToken((payload as { csrfToken?: string | null }).csrfToken);
  }
  return payload as T;
}

export function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { headers: { Accept: 'application/json' }, signal });
}

type SendOptions = { signal?: AbortSignal; headers?: Record<string, string> };

async function sendJson<T>(method: 'POST' | 'PUT' | 'DELETE', path: string, body: unknown, options: SendOptions): Promise<T> {
  const { signal, headers } = options;
  if (csrfToken === null) await getJson('/auth/session', signal);
  return request<T>(path, {
    method,
    headers: {
      Accept: 'application/json',
      ...headers,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(csrfToken === null ? {} : { 'X-CSRF-Token': csrfToken }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
}

export const postJson = <T = null>(path: string, body?: unknown, options: SendOptions = {}) =>
  sendJson<T>('POST', path, body, options);

export const putJson = <T = null>(path: string, body?: unknown, options: SendOptions = {}) =>
  sendJson<T>('PUT', path, body, options);

export const deleteJson = <T = null>(path: string, options: SendOptions = {}) =>
  sendJson<T>('DELETE', path, undefined, options);
