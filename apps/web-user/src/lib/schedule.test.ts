// 강좌 일정 행 목록을 시안의 '요일 / 시간' 두 줄 표기로 바꾸는 규칙을 시안의 실제 패턴으로 확인하는 시험
import { describe, expect, it } from 'vitest';
import { COURSE_SEEDS } from '../mocks/courseData';
import { formatSchedule, type ScheduleSlot } from './schedule';

const slot = (days: ScheduleSlot['days'], startTime: string, endTime: string, label: string | null = null): ScheduleSlot => ({
  days,
  startTime,
  endTime,
  label,
});

describe('formatSchedule', () => {
  it('같은 시간에 여러 요일이면 요일을 점으로 잇고 시간은 한 줄이다', () => {
    expect(formatSchedule([slot(['TUE', 'THU'], '10:00', '11:30')])).toEqual({
      days: '화·목',
      times: '10:00~11:30',
    });
  });

  it('요일은 입력 순서와 관계없이 월요일부터 정렬한다', () => {
    expect(formatSchedule([slot(['THU', 'TUE'], '10:00', '11:30')]).days).toBe('화·목');
  });

  it('월요일부터 금요일까지 모두면 월~금으로 줄인다', () => {
    expect(formatSchedule([slot(['MON', 'TUE', 'WED', 'THU', 'FRI'], '10:00', '21:00')])).toEqual({
      days: '월~금',
      times: '10:00~21:00',
    });
  });

  it('요일마다 시간이 다르면 시간 줄에 요일을 괄호로 붙인다 (한국무용)', () => {
    expect(
      formatSchedule([slot(['WED'], '12:00', '13:30'), slot(['FRI'], '10:00', '11:30')]),
    ).toEqual({ days: '수·금', times: '(수)12:00~13:30 / (금)10:00~11:30' });
  });

  it('같은 요일에 반이 나뉘면 요일 줄에 반 이름을 괄호로 붙이고 요일은 한 번만 쓴다 (오카리나)', () => {
    expect(
      formatSchedule([slot(['WED'], '10:00', '11:30', '중급'), slot(['WED'], '11:30', '13:00', '초급')]),
    ).toEqual({ days: '수(중급) / (초급)', times: '10:00~11:30 / 11:30~13:00' });
  });

  it('반 이름의 순서를 바꾸지 않는다 (캘리그라피)', () => {
    expect(
      formatSchedule([slot(['WED'], '14:00', '15:30', '초급'), slot(['WED'], '15:30', '17:00', '중급')]),
    ).toEqual({ days: '수(초급) / (중급)', times: '14:00~15:30 / 15:30~17:00' });
  });

  it('요일이 다른 반은 요일을 다시 쓴다', () => {
    expect(
      formatSchedule([slot(['TUE'], '10:00', '11:00', '초급'), slot(['THU'], '10:00', '11:00', '중급')]).days,
    ).toBe('화(초급) / 목(중급)');
  });

  it('일정이 없으면 지어내지 않고 미기재로 표시한다', () => {
    expect(formatSchedule([])).toEqual({ days: '일정 미기재', times: '' });
  });
});

describe('시안 25개 강좌 전체', () => {
  // 시안 courses.html에 실제로 적힌 요일·시간 표기. 구분 기호만 점(·)으로 통일했다.
  const expected: Record<string, [string, string]> = {
    초급컴퓨터: ['화·목', '10:00~11:30'],
    생활영어: ['화·목', '11:30~13:00'],
    '라인댄스 A': ['월·목', '14:00~15:30'],
    '통 기 타': ['월·화', '19:00~20:30'],
    한글문해교실: ['화·목', '13:30~15:20'],
    한국무용: ['수·금', '(수)12:00~13:30 / (금)10:00~11:30'],
    기공체조반: ['수·금', '16:00~17:30'],
    오카리나: ['수(중급) / (초급)', '10:00~11:30 / 11:30~13:00'],
    캘리그라피: ['수(초급) / (중급)', '14:00~15:30 / 15:30~17:00'],
    헬스: ['월~금', '10:00~21:00'],
  };

  it('샘플 25개를 시안과 같은 두 줄로 표기한다', () => {
    expect(COURSE_SEEDS).toHaveLength(25);
    const checked: string[] = [];
    for (const seed of COURSE_SEEDS) {
      const want = expected[seed.name];
      if (!want) continue;
      const got = formatSchedule(seed.schedules);
      expect([got.days, got.times], seed.name).toEqual(want);
      checked.push(seed.name);
    }
    expect(checked.sort()).toEqual(
      ['초급컴퓨터', '생활영어', '라인댄스 A', '통 기 타', '한글문해교실', '한국무용', '기공체조반', '오카리나', '캘리그라피', '헬스'].sort(),
    );
  });

  it('25개 모두 표기를 만들 수 있고 시간 줄이 비어 있지 않다', () => {
    for (const seed of COURSE_SEEDS) {
      const text = formatSchedule(seed.schedules);
      expect(text.days, seed.name).not.toBe('일정 미기재');
      expect(text.times, seed.name).toMatch(/\d{2}:\d{2}~\d{2}:\d{2}/);
    }
  });
});
