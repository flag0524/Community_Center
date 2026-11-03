// 문의·후기의 작성·수정·삭제 요청. 작성은 같은 시도가 두 번 접수되지 않도록 멱등키를 싣는다
import type { Schemas } from '@jori/api-client';
import { deleteJson, postJson, putJson } from './http';

export type InquiryDetail = Schemas['InquiryDetail'];
export type ReviewDetail = Schemas['ReviewDetail'];
export type InquiryWrite = Schemas['InquiryWrite'];
export type ReviewWrite = Schemas['ReviewWrite'];

const keyed = (idempotencyKey: string) => ({ headers: { 'Idempotency-Key': idempotencyKey } });

export const createInquiry = (body: InquiryWrite, idempotencyKey: string) =>
  postJson<InquiryDetail>('/me/inquiries', body, keyed(idempotencyKey));
export const updateInquiry = (postId: string, body: InquiryWrite) =>
  putJson<InquiryDetail>(`/me/inquiries/${encodeURIComponent(postId)}`, body);
export const deleteInquiry = (postId: string) => deleteJson(`/me/inquiries/${encodeURIComponent(postId)}`);

export const createReview = (body: ReviewWrite, idempotencyKey: string) =>
  postJson<ReviewDetail>('/me/reviews', body, keyed(idempotencyKey));
export const updateReview = (postId: string, body: ReviewWrite) =>
  putJson<ReviewDetail>(`/me/reviews/${encodeURIComponent(postId)}`, body);
export const deleteReview = (postId: string) => deleteJson(`/me/reviews/${encodeURIComponent(postId)}`);