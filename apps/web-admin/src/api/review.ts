// 강사 심사 요청. 방문·외부 접수 등록은 멱등키를 싣고 심사는 읽은 버전을 함께 보낸다
import type { Schemas } from '@jori/api-client';
import { postJson, putJson } from './http';

export type InstructorReview = Schemas['InstructorReview'];
export type InstructorReviewCreate = Schemas['InstructorReviewCreate'];
export type InstructorReviewWrite = Schemas['InstructorReviewWrite'];

export const createInstructorReview = (body: InstructorReviewCreate, key: string) =>
  postJson<InstructorReview>('/instructor-applications', body, { headers: { 'Idempotency-Key': key } });

export const reviewInstructor = (applicationId: string, body: InstructorReviewWrite) =>
  putJson<InstructorReview>(`/instructor-applications/${encodeURIComponent(applicationId)}`, body);