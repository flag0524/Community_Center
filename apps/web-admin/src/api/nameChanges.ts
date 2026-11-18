// 회원 이름 변경 요청의 승인·반려 요청. 처리 메모는 회원에게도 보인다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type AdminNameChange = Schemas['AdminNameChange'];

export const decideNameChange = (requestId: string, action: 'approve' | 'reject', note: string) =>
  postJson<AdminNameChange>(`/name-change-requests/${encodeURIComponent(requestId)}/${action}`, note.trim() ? { note: note.trim() } : {});
