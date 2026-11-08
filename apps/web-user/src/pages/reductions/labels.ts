// 감면 유형과 심사 상태를 화면 문구로 옮긴다
import type { Schemas } from '@jori/api-client';

export const REDUCTION_TYPE_LABEL: Record<Schemas['ReductionType'], string> = {
  LIVELIHOOD: '기초생활보장 수급자 본인',
  VETERAN: '국가유공자 본인',
  DISABLED: '등록 장애인 본인',
};

export const REDUCTION_STATUS_LABEL: Record<Schemas['ReductionStatus'], string> = {
  RECEIVED: '접수',
  APPROVED: '승인',
  REJECTED: '반려',
  REVOKED: '철회',
};