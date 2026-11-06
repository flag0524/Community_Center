// 감면 심사 요청. 결정은 읽은 버전을, 재심사는 멱등키를 싣는다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type ReductionReview = Schemas['ReductionReview'];
export type ReductionDecisionRequest = Schemas['ReductionDecisionRequest'];

export const viewEvidence = (reviewId: string, fileId: string) => postJson<ReductionReview>(`/reductions/${encodeURIComponent(reviewId)}/evidence-views`, { fileId });
export const decideReduction = (reviewId: string, body: ReductionDecisionRequest) => postJson<ReductionReview>(`/reductions/${encodeURIComponent(reviewId)}/decision`, body);
export const reReviewReduction = (reviewId: string, key: string) => postJson<ReductionReview>(`/reductions/${encodeURIComponent(reviewId)}/re-review`, undefined, { headers: { 'Idempotency-Key': key } });