// 강좌 화면이 함께 쓰는 문구와 형식. 상태 판정은 서버가 하고 여기서는 글자로만 옮긴다
import type { Schemas } from '@jori/api-client';

export type EducationState = Schemas['EducationState'];

export const EDUCATION_LABEL: Record<EducationState, string> = {
  UPCOMING: '교육예정',
  ONGOING: '교육중',
  ENDED: '교육종료',
};

/** 시안이 강사명이 공란인 강좌(헬스)에 쓰는 문구 */
export const NO_INSTRUCTOR = '시간표 미기재';

export const instructorText = (name: string | null): string => name ?? NO_INSTRUCTOR;

export const categoryText = (category: { name: string } | null): string => category?.name ?? '분야 미확인';

export const formatFee = (fee: number): string => `${fee.toLocaleString('ko-KR')}원`;

/** 잔여석은 접수중일 때만 의미가 있다. 접수마감·접수예정에서는 숨긴다(D14). */
export function remainingSeatsText(course: {
  receptionState: Schemas['ReceptionState'];
  remainingSeats?: number | null;
}): string | null {
  if (course.receptionState !== 'OPEN' || course.remainingSeats == null) return null;
  return `잔여 ${course.remainingSeats}석`;
}
