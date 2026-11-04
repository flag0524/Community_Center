// 모집·지원 상태를 화면 문구로 옮긴다
import type { Schemas } from '@jori/api-client';

export const RECRUITMENT_STATUS_LABEL: Record<Schemas['RecruitmentStatus'], string> = {
  UPCOMING: '모집예정',
  OPEN: '모집중',
  CLOSED: '모집마감',
};

export const APPLY_STATUS_LABEL: Record<Schemas['InstructorApplyStatus'], string> = {
  REVIEWING: '서류 검토중',
  SUPPLEMENT: '보완요청',
  INTERVIEW: '심사중',
  SELECTED: '선정',
  REJECTED: '미선정',
};

export const INSTRUCTOR_GROUP_TITLE = '강사은행';