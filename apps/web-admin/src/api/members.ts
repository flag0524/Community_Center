// 회원 조회 화면의 기록 요청. 원문 보기는 사유를 남기고 검토 기록은 멱등키를 싣는다. 회원 정보를 고치는 요청은 없다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type MemberContact = Schemas['MemberContact'];
export type MemberReview = Schemas['MemberReview'];
export type MemberReviewCreate = Schemas['MemberReviewCreate'];
export type AdminMember = Schemas['AdminMember'];

const id = encodeURIComponent;

export const revealMemberContact = (memberId: string, reason: string) => postJson<MemberContact>(`/members/${id(memberId)}/reveal`, { reason });
export const createMemberReview = (memberId: string, body: MemberReviewCreate, key: string) =>
  postJson<MemberReview>(`/members/${id(memberId)}/reviews`, body, { headers: { 'Idempotency-Key': key } });
export const closeMemberReview = (memberId: string, reviewId: string, note: string) =>
  postJson<MemberReview>(`/members/${id(memberId)}/reviews/${id(reviewId)}/close`, { note });
export const recordResidence = (memberId: string, result: Schemas['ResidenceStatus'], note: string) =>
  postJson<AdminMember>(`/members/${id(memberId)}/residence`, { result, note });