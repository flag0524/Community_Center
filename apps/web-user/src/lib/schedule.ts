// 강좌 일정 행 목록을 시안의 '요일 / 시간' 두 줄 표기로 바꾸는 규칙
import type { Schemas } from '@jori/api-client';

export type ScheduleSlot = Schemas['ScheduleSlot'];
export type Weekday = Schemas['Weekday'];

const ORDER: Weekday[] = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];
const LABEL: Record<Weekday, string> = {
  MON: '월',
  TUE: '화',
  WED: '수',
  THU: '목',
  FRI: '금',
  SAT: '토',
  SUN: '일',
};

/** 요일 선택지처럼 화면이 요일 이름을 직접 쓸 때 사용한다. */
export const WEEKDAY_LABEL = LABEL;

const sortDays = (days: Weekday[]) => [...new Set(days)].sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b));

const MON_TO_FRI = ORDER.slice(0, 5).join();

/** 월~금을 모두 채우면 줄여 쓰고 아니면 점으로 잇는다. */
function daysText(days: Weekday[]): string {
  const sorted = sortDays(days);
  if (sorted.join() === MON_TO_FRI) return '월~금';
  return sorted.map((day) => LABEL[day]).join('·');
}

const range = (slot: ScheduleSlot) => `${slot.startTime}~${slot.endTime}`;

export interface ScheduleText {
  /** 요일 줄. 반이 나뉜 강좌는 '수(중급) / (초급)'처럼 반 이름이 붙는다. */
  days: string;
  /** 시간 줄. 요일마다 시간이 다르면 '(수)12:00~13:30 / (금)10:00~11:30'처럼 요일이 붙는다. */
  times: string;
}

export function formatSchedule(slots: ScheduleSlot[]): ScheduleText {
  if (slots.length === 0) return { days: '일정 미기재', times: '' };

  // 같은 요일에 반이 나뉜 강좌. 요일은 바뀔 때만 쓰고 반 이름은 항상 붙인다.
  if (slots.some((slot) => slot.label)) {
    let previous = '';
    const parts = slots.map((slot) => {
      const current = daysText(slot.days);
      const head = current === previous ? '' : current;
      previous = current;
      return `${head}${slot.label ? `(${slot.label})` : ''}`;
    });
    return { days: parts.join(' / '), times: slots.map(range).join(' / ') };
  }

  const allDays = slots.flatMap((slot) => slot.days);
  const sameTime = slots.every((slot) => range(slot) === range(slots[0]!));
  if (sameTime) return { days: daysText(allDays), times: range(slots[0]!) };

  // 요일마다 시간이 다른 강좌
  return {
    days: daysText(allDays),
    times: slots.map((slot) => `(${sortDays(slot.days).map((day) => LABEL[day]).join('·')})${range(slot)}`).join(' / '),
  };
}
