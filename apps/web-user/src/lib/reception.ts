// 서버가 판정한 접수 상태를 화면 문구로 옮긴다. 상태 자체는 계산하지 않는다
import type { Schemas } from '@jori/api-client';

export type ReceptionState = Schemas['ReceptionState'];

export const RECEPTION_LABEL: Record<ReceptionState, string> = {
  OPEN: '접수중',
  UPCOMING: '접수예정',
  CLOSED: '접수마감',
};

// 쉬운 화면 안내 문장에 쓰는 서술형
export const RECEPTION_SENTENCE: Record<ReceptionState, string> = {
  OPEN: '접수 중입니다.',
  UPCOMING: '접수 예정입니다.',
  CLOSED: '접수가 마감되었습니다.',
};
