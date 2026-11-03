// 모의 서버가 다음 결제 승인 확인에 돌려줄 결과. 개발 서버에서만 주소의 mockPay로 고른다
export type PayOutcome = 'success' | 'failed' | 'unknown' | 'expired';

const STORAGE_KEY = 'mockPay';
const OUTCOMES: readonly PayOutcome[] = ['success', 'failed', 'unknown', 'expired'];

let override: PayOutcome | null = null;

const isOutcome = (value: string | null): value is PayOutcome => OUTCOMES.includes(value as PayOutcome);

/** 시험에서 결과를 고정한다. null이면 해제한다. */
export function setMockPayOutcome(value: PayOutcome | null): void {
  override = value;
}

export function mockPayOutcome(): PayOutcome {
  if (override) return override;
  try {
    const stored = window.sessionStorage.getItem(STORAGE_KEY);
    return isOutcome(stored) ? stored : 'success';
  } catch {
    return 'success';
  }
}

/**
 * 주소의 ?mockPay=failed 를 읽어 세션에 기억한다. 빈 값(?mockPay=)이면 해제하고 모르는 값은 무시한다.
 * 개발 서버에서만 호출되며 운영 빌드에는 들어가지 않는다.
 */
export function initMockPayFromLocation(): void {
  try {
    const param = new URLSearchParams(window.location.search).get('mockPay');
    if (param === null) return;
    if (param === '') window.sessionStorage.removeItem(STORAGE_KEY);
    else if (isOutcome(param)) window.sessionStorage.setItem(STORAGE_KEY, param);
  } catch {
    // 저장소를 쓸 수 없으면 성공으로 본다.
  }
}
