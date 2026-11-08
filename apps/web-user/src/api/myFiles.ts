// 회원이 자기 지원서·문의에 올리는 첨부 요청. 업무를 먼저 저장한 뒤 파일을 한 개씩 올리고 제거는 논리삭제다
import type { Schemas } from '@jori/api-client';
import { deleteJson, postForm } from './http';

export type MyFile = Schemas['MyFile'];
export type MyFileList = Schemas['MyFileList'];

export const uploadMyFile = (ownerPath: string, file: File, key: string) => {
  const form = new FormData();
  form.append('file', file);
  return postForm<MyFile>(`${ownerPath}/files`, form, { headers: { 'Idempotency-Key': key } });
};
export const deleteMyFile = (fileId: string) => deleteJson(`/me/files/${encodeURIComponent(fileId)}`);
export const myFileUrl = (fileId: string) => `/api/v1/me/files/${encodeURIComponent(fileId)}`;