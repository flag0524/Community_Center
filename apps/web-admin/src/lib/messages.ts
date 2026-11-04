// 서버가 필드별로 돌려준 오류를 화면에 보일 문장으로 합치는 도우미
import { ApiRequestError } from '../api/http';

/** 필드 이름에 맞는 입력칸이 없는 서버 오류(예: schedule)까지 한 문장으로 모은다. */
export function allFieldMessages(error: unknown): string {
  return error instanceof ApiRequestError ? Object.values(error.body?.fields ?? {}).join(' ') : '';
}

export const isVersionConflict = (error: unknown): boolean =>
  error instanceof ApiRequestError && error.body?.code === 'VERSION_CONFLICT';