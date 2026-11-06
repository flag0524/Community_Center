// 홈·센터 콘텐츠 요청. 만들기는 멱등키를 싣고 고치기는 읽은 버전을 함께 보낸다
import type { Schemas } from '@jori/api-client';
import { postJson, putJson } from './http';

export type AdminContent = Schemas['AdminContent'];
export type AdminContentWrite = Schemas['AdminContentWrite'];
export type ContactFields = Schemas['ContactFields'];

export const createContent = (body: AdminContentWrite, key: string) => postJson<AdminContent>('/contents', body, { headers: { 'Idempotency-Key': key } });
export const updateContent = (contentId: string, body: AdminContentWrite, version: number) =>
  putJson<AdminContent>(`/contents/${encodeURIComponent(contentId)}`, { ...body, version });