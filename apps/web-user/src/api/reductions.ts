// 회원의 감면 사전심사 요청. 신청은 멱등키를 싣고 금액·비율은 보내지 않는다. 증빙은 신청한 뒤에 올린다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type MyReduction = Schemas['MyReduction'];
export type MyReductionCreate = Schemas['MyReductionCreate'];

export const createReduction = (body: MyReductionCreate, key: string) => postJson<MyReduction>('/me/reduction-reviews', body, { headers: { 'Idempotency-Key': key } });
export const withdrawReduction = (reviewId: string) => postJson<MyReduction>(`/me/reduction-reviews/${encodeURIComponent(reviewId)}/withdraw`);