// 서버가 준 상태 코드를 화면 문구로 바꾸는 표. 상태 판정은 서버가 하고 화면은 이름만 붙인다
import type { Schemas } from '@jori/api-client';

export const COURSE_STATUS: Record<Schemas['CourseAdminStatus'], string> = {
  DRAFT: '작성중',
  PUBLISHED: '공개',
  RECEPTION_CLOSED: '접수마감',
  CANCELLED: '폐강',
};

export const RECEPTION_STATE: Record<Schemas['ReceptionState'], string> = {
  UPCOMING: '접수예정',
  OPEN: '접수중',
  CLOSED: '접수종료',
};

export const EDUCATION_STATE: Record<Schemas['EducationState'], string> = {
  UPCOMING: '교육예정',
  ONGOING: '교육중',
  ENDED: '교육종료',
};

export const CYCLE_STATUS: Record<Schemas['CycleStatus'], string> = {
  DRAFT: '작성중',
  ACTIVE: '사용중',
  INACTIVE: '사용중지',
};