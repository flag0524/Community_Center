// 작업이력 코드·대상 한글 표시 시험. 모르는 값은 코드 그대로 보여야 한다
import { describe, expect, it } from 'vitest';
import { jobLabel, targetLabel } from './auditLabels';

describe('작업이력 한글 표시', () => {
  it('작업 코드를 한글로 바꾸고 모르는 코드는 그대로 둔다', () => {
    expect(jobLabel('FCLT_CREATE')).toBe('시설 등록');
    expect(jobLabel('APLY_PROMOTE')).toBe('대기 승격');
    expect(jobLabel('SOMETHING_NEW')).toBe('SOMETHING_NEW');
  });

  it('이미 한글인 작업명은 그대로 둔다', () => {
    expect(jobLabel('환불 승인')).toBe('환불 승인');
  });

  it('대상의 테이블 이름만 바꾸고 번호는 남긴다', () => {
    expect(targetLabel('TB_FCLT 12')).toBe('시설 12');
    expect(targetLabel('TB_FCLT')).toBe('시설');
    expect(targetLabel('건강요가 초급')).toBe('건강요가 초급');
    expect(targetLabel('TB_UNKNOWN 3')).toBe('TB_UNKNOWN 3');
  });
});
