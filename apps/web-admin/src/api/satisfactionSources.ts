// 강좌 만족도 집계자료 등록과 승인·반려 요청. 등록은 멱등키를 함께 보낸다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type SatisfactionCreate = Schemas['SatisfactionSourceCreate'];
export type SatisfactionDetail = Schemas['SatisfactionSourceDetail'];

export const createSatisfactionSource = (body: SatisfactionCreate, key: string) =>
  postJson<SatisfactionDetail>('/stats/satisfaction/sources', body, { headers: { 'Idempotency-Key': key } });

export const decideSatisfactionSource = (sourceId: string, action: 'approve' | 'reject') =>
  postJson<SatisfactionDetail>(`/stats/satisfaction/sources/${encodeURIComponent(sourceId)}/${action}`);
