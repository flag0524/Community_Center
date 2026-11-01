// 인증 요청 도우미가 토큰 교체와 요청 순서를 지키는지 확인하는 시험
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';
import { server, useMockServer } from '../test/render';
import { logout } from './auth';
import { postJson, rememberCsrfToken } from './http';

useMockServer();

describe('logout', () => {
  it('로그아웃 직후의 다음 요청은 옛 토큰을 보내지 않고 세션에서 새 토큰을 먼저 받는다', async () => {
    const calls: string[] = [];
    server.use(
      http.post('/api/v1/auth/logout', () => {
        calls.push('logout');
        return new HttpResponse(null, { status: 204 });
      }),
      http.get('/api/v1/auth/session', () => {
        calls.push('session');
        return HttpResponse.json({ authenticated: false, csrfToken: 'new-token', serverNow: '2026-09-01T00:00:00Z' });
      }),
      http.post('/api/v1/echo', ({ request }) => {
        calls.push(`echo:${request.headers.get('X-CSRF-Token')}`);
        return HttpResponse.json({});
      }),
    );
    rememberCsrfToken('old-token');

    await logout();
    await postJson('/echo', {});

    // 서버가 로그아웃 때 토큰을 바꾸므로 옛 토큰으로 echo가 나가면 안 된다.
    expect(calls).toEqual(['logout', 'session', 'echo:new-token']);
  });
});
