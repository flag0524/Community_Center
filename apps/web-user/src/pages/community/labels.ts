// 문의 상태를 화면 문구로 옮긴다
import type { Schemas } from '@jori/api-client';

export const INQUIRY_STATUS_LABEL: Record<Schemas['InquiryStatus'], string> = {
  RECEIVED: '접수',
  ANSWERED: '답변완료',
};