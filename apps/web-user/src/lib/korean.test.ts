// 받침 유무로 목적격 조사(을/를)를 고르는 함수를 화면에 쓰는 낱말로 확인하는 시험
import { describe, expect, it } from 'vitest';
import { withObject } from './korean';

describe('withObject', () => {
  it.each([
    ['강좌 정보', '강좌 정보를'],
    ['강좌 목록', '강좌 목록을'],
    ['강의계획서', '강의계획서를'],
    ['분야별 강좌', '분야별 강좌를'],
    ['센터 소식', '센터 소식을'],
    ['연락처', '연락처를'],
    ['신청 내역', '신청 내역을'],
  ])('%s 뒤에는 알맞은 조사를 붙인다', (word, expected) => {
    expect(withObject(word)).toBe(expected);
  });

  it('한글이 아닌 글자로 끝나면 를을 쓰지 않고 낱말만 돌려준다', () => {
    expect(withObject('FAQ')).toBe('FAQ');
    expect(withObject('')).toBe('');
  });
});
