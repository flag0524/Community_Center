// 감면 심사 요청. 결정은 읽은 버전을, 재심사는 멱등키를 싣는다. 증빙은 파일 내려받기로 열람한다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type ReductionReview = Schemas['ReductionReview'];
export type ReductionDecisionRequest = Schemas['ReductionDecisionRequest'];

export const decideReduction = (reviewId: string, body: ReductionDecisionRequest) => postJson<ReductionReview>(`/reductions/${encodeURIComponent(reviewId)}/decision`, body);
export const reReviewReduction = (reviewId: string, key: string) => postJson<ReductionReview>(`/reductions/${encodeURIComponent(reviewId)}/re-review`, undefined, { headers: { 'Idempotency-Key': key } });