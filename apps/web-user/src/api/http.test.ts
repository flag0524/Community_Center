// fetch 도우미의 CSRF 토큰 처리와 오류 변환 시험
import { HttpResponse, http } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';
import { server, useMockServer } from '../test/render';
import { ApiRequestError, getJson, postJson, rememberCsrfToken } from './http';

useMockServer();

beforeEach(() => rememberCsrfToken(null));

describe('postJson', () => {
  it('기억한 토큰을 X-CSRF-Token 헤더에, 본문을 JSON으로 보낸다', async () => {
    let seen: { token: string | null; type: string | null; body: unknown } | null = null;
    server.use(
      http.post('/api/v1/echo', async ({ request }) => {
        seen = {
          token: request.headers.get('X-CSRF-Token'),
          type: request.headers.get('Content-Type'),
          body: await request.json(),
        };
        return HttpResponse.json({ ok: true });
      }),
    );
    rememberCsrfToken('token-1');

    await expect(postJson('/echo', { a: 1 })).resolves.toEqual({ ok: true });

    expect(seen).toEqual({ token: 'token-1', type: 'application/json', body: { a: 1 } });
  });

  it('토큰이 없으면 세션을 먼저 조회해 토큰을 얻은 뒤 한 번만 조회한다', async () => {
    let sessionCalls = 0;
    const tokens: Array<string | null> = [];
    server.use(
      http.get('/api/v1/auth/session', () => {
        sessionCalls += 1;
        return HttpResponse.json({ authenticated: false, csrfToken: 'from-session', serverNow: '2026-09-01T00:00:00Z' });
      }),
      http.post('/api/v1/echo', ({ request }) => {
        tokens.push(request.headers.get('X-CSRF-Token'));
        return HttpResponse.json({});
      }),
    );

    await postJson('/echo', {});
    await postJson('/echo', {});

    expect(tokens).toEqual(['from-session', 'from-session']);
    expect(sessionCalls).toBe(1);
  });

  it('204 응답은 null을 돌려준다', async () => {
    server.use(http.post('/api/v1/echo', () => new HttpResponse(null, { status: 204 })));
    rememberCsrfToken('t');
    await expect(postJson('/echo')).resolves.toBeNull();
  });

  it('오류 응답은 ApiRequestError로 바꿔 던지고 본문의 코드와 필드를 보존한다', async () => {
    server.use(
      http.post('/api/v1/echo', () =>
        HttpResponse.json(
          { code: 'LOGIN_FAILED', message: '아이디 또는 비밀번호를 확인해 주세요.', fields: { loginId: '확인' }, requestId: 'r1' },
          { status: 401 },
        ),
      ),
    );
    rememberCsrfToken('t');

    const error = await postJson('/echo', {}).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({ status: 401, body: { code: 'LOGIN_FAILED', fields: { loginId: '확인' } } });
  });
});

describe('getJson', () => {
  it('세션 응답을 받으면 토큰을 기억한다', async () => {
    let seen: string | null = null;
    server.use(
      http.get('/api/v1/auth/session', () =>
        HttpResponse.json({ authenticated: false, csrfToken: 'remembered', serverNow: '2026-09-01T00:00:00Z' }),
      ),
      http.post('/api/v1/echo', ({ request }) => {
        seen = request.headers.get('X-CSRF-Token');
        return HttpResponse.json({});
      }),
    );

    await getJson('/auth/session');
    await postJson('/echo', {});

    expect(seen).toBe('remembered');
  });
});
