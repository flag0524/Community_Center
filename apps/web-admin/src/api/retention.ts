// 보존·파기 실행 요청. 사용자가 확인한 건수와 멱등키를 함께 보낸다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type RetentionDetail = Schemas['RetentionDetail'];

export const executeRetention = (itemId: string, expectedCount: number, key: string) =>
  postJson<RetentionDetail>(`/retention/${encodeURIComponent(itemId)}/execute`, { expectedCount }, { headers: { 'Idempotency-Key': key } });