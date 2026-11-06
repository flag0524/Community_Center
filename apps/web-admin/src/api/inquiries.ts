// 문의 답변 요청. 답변을 쓰거나 고칠 때 읽은 답변 버전을 함께 보내고, 아직 답변이 없으면 0을 보낸다
import type { Schemas } from '@jori/api-client';
import { putJson } from './http';

export type AdminInquiry = Schemas['AdminInquiry'];

export const answerInquiry = (inquiryId: string, content: string, relatedLink: string | null, version: number) =>
  putJson<AdminInquiry>(`/inquiries/${encodeURIComponent(inquiryId)}/answer`, { content, relatedLink, version });