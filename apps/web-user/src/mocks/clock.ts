// 모의 서버가 '지금'으로 보는 시각. 개발 서버에서만 주소의 mockNow로 옮겨 접수 상태를 시연한다
const STORAGE_KEY = 'mockNow';

let override: Date | null = null;

/** 시험에서 시각을 고정한다. null이면 해제한다. */
export function setMockNow(value: Date | null): void {
  override = value;
}

function parseMockNow(text: string): Date | null {
  // 날짜만 쓰면 그날 한국시간 정오로 본다. 접수 기간 안에 들어가 시연하기 쉽다.
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(text) ? `${text}T12:00:00+09:00` : text;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function readStored(): Date | null {
  try {
    const stored = window.sessionStorage.getItem(STORAGE_KEY);
    return stored ? parseMockNow(stored) : null;
  } catch {
    return null;
  }
}

export function mockNow(): Date {
  return override ? new Date(override) : (readStored() ?? new Date());
}

/**
 * 주소의 ?mockNow=2026-09-08 을 읽어 세션에 기억한다. 빈 값(?mockNow=)이면 해제한다.
 * 잘못된 값은 무시한다. 개발 서버에서만 호출되며 운영 빌드에는 들어가지 않는다.
 */
export function initMockClockFromLocation(): void {
  try {
    const param = new URLSearchParams(window.location.search).get('mockNow');
    if (param === null) return;
    if (param === '') window.sessionStorage.removeItem(STORAGE_KEY);
    else if (parseMockNow(param)) window.sessionStorage.setItem(STORAGE_KEY, param);
  } catch {
    // 저장소를 쓸 수 없으면 실제 시각을 쓴다.
  }
}
