// 약관·동의문 버전 요청. 만들기는 멱등키를 싣고 고치기·확정·게시는 읽은 버전을 함께 보낸다
import type { Schemas } from '@jori/api-client';
import { postJson, putJson } from './http';

export type TermVersion = Schemas['TermVersion'];
export type TermVersionCreate = Schemas['TermVersionCreate'];

export const createTermVersion = (termType: Schemas['TermType'], body: TermVersionCreate, key: string) =>
  postJson<TermVersion>(`/terms/${termType}/versions`, body, { headers: { 'Idempotency-Key': key } });
export const updateTermVersion = (versionId: string, body: Omit<Schemas['TermVersionUpdate'], 'version'>, version: number) =>
  putJson<TermVersion>(`/terms/versions/${encodeURIComponent(versionId)}`, { ...body, version });
export const fixTermVersion = (versionId: string, version: number) => postJson<TermVersion>(`/terms/versions/${encodeURIComponent(versionId)}/fix`, { version });
export const publishTermVersion = (versionId: string, version: number) => postJson<TermVersion>(`/terms/versions/${encodeURIComponent(versionId)}/publish`, { version });