import { afterEach, describe, expect, it, vi } from 'vitest';
import { requestOtp } from '../api/auth';
import { useMockServer } from '../test/render';

useMockServer();
afterEach(() => vi.restoreAllMocks());

describe('전화번호별 OTP 재전송 제한', () => {
  it('목적과 회원 존재 여부가 달라도 60초 이내에는 차단한다', async () => {
    const clock = vi.spyOn(Date, 'now').mockReturnValue(1_800_000_000_000);
    await requestOtp('ID_FIND', '01012345678', '없는회원');
    clock.mockReturnValue(1_800_000_059_999);
    await expect(requestOtp('JOIN', '01012345678', '가입회원')).rejects.toMatchObject({
      status: 429, body: { code: 'OTP_RESEND_TOO_SOON' },
    });
    clock.mockReturnValue(1_800_000_060_000);
    await expect(requestOtp('PASSWORD_RESET', '01012345678', '없는회원', 'missing')).resolves.toBeDefined();
  });

  it('다른 전화번호는 같은 시각에도 발급한다', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(1_800_000_000_000);
    await requestOtp('JOIN', '01012345678', '가입회원');
    await expect(requestOtp('JOIN', '01099998888', '다른회원')).resolves.toBeDefined();
  });
});
