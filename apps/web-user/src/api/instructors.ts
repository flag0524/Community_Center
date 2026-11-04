// 강사 지원서 작성·수정 요청. 작성은 같은 시도가 두 번 접수되지 않도록 멱등키를 싣는다
import type { Schemas } from '@jori/api-client';
import { postJson, putJson } from './http';

export type InstructorApplication = Schemas['InstructorApplication'];
export type InstructorApplyWrite = Schemas['InstructorApplyWrite'];

export const createInstructorApplication = (body: InstructorApplyWrite, idempotencyKey: string) =>
  postJson<InstructorApplication>('/me/instructor-applications', body, { headers: { 'Idempotency-Key': idempotencyKey } });

export const updateInstructorApplication = (applicationId: string, body: InstructorApplyWrite) =>
  putJson<InstructorApplication>(`/me/instructor-applications/${encodeURIComponent(applicationId)}`, body);