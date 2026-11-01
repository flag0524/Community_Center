// 요청 실패를 화면에 보일 문장으로 바꾸는 도우미
import { ApiRequestError } from '../api/http';

export const NETWORK_ERROR_MESSAGE = '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.';

/** 서버가 준 문구를 우선하고, 연결 자체가 실패하면 연결 안내를 쓴다. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) return error.body?.message ?? error.message;
  return NETWORK_ERROR_MESSAGE;
}
