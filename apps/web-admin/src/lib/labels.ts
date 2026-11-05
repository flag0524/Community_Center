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

export const WEEKDAY: Record<Schemas['Weekday'], string> = {
  MON: '월',
  TUE: '화',
  WED: '수',
  THU: '목',
  FRI: '금',
  SAT: '토',
  SUN: '일',
};

export const CHANGE_KIND: Record<Schemas['ScheduleChangeKind'], string> = { CANCEL: '휴강', MAKEUP: '보강' };

export const FACILITY_KIND: Record<Schemas['FacilityKind'], string> = { CENTER: '센터', ROOM: '강의실' };

export const REVIEW_STATUS: Record<Schemas['ReviewStatus'], string> = {
  PENDING: '심사대기',
  APPROVED: '승인',
  REJECTED: '반려',
  SUSPENDED: '활동중지',
};

export const APPLICATION_SOURCE: Record<Schemas['ApplicationSource'], string> = {
  ONLINE: '온라인 지원',
  VISIT: '방문 접수',
  EXTERNAL: '외부 접수',
};

export const INPUT_STATUS: Record<Schemas['AttendanceInputStatus'], string> = { IN_PROGRESS: '입력중', DONE: '완료' };

export const ATTENDANCE_MARK: Record<Schemas['AttendanceMark'], string> = { PRESENT: '출석', ABSENT: '결석', UNCHECKED: '미체크' };
