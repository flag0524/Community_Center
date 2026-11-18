// 연령·성별 집계자료 등록과 승인·반려 요청. 등록은 멱등키를 함께 보낸다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type SourceCreate = Schemas['SourceCreate'];
export type SourceDetail = Schemas['SourceDetail'];

export const createSource = (body: SourceCreate, key: string) =>
  postJson<SourceDetail>('/stats/age-gender/sources', body, { headers: { 'Idempotency-Key': key } });

export const decideSource = (sourceId: string, action: 'approve' | 'reject') =>
  postJson<SourceDetail>(`/stats/age-gender/sources/${encodeURIComponent(sourceId)}/${action}`);
