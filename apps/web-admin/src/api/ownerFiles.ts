// 소유 업무 화면의 첨부 요청. 업무를 먼저 저장한 뒤 파일을 한 개씩 올리고 제거는 논리삭제다
import type { Schemas } from '@jori/api-client';
import { deleteJson, postForm } from './http';

export type OwnerFile = Schemas['OwnerFile'];
export type OwnerFileList = Schemas['OwnerFileList'];

export const uploadOwnerFile = (ownerPath: string, file: File, key: string) => {
  const form = new FormData();
  form.append('file', file);
  return postForm<OwnerFile>(`${ownerPath}/files`, form, { headers: { 'Idempotency-Key': key } });
};
export const deleteOwnerFile = (fileId: string) => deleteJson(`/files/${encodeURIComponent(fileId)}`);
export const downloadUrl = (fileId: string) => `/api/admin/v1/files/${encodeURIComponent(fileId)}/download`;