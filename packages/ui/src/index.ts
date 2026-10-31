// 기본 화면과 쉬운 화면 구분처럼 주민 앱 전체가 공유하는 화면 모드 정의
export const VIEW_MODES = ['standard', 'easy'] as const;

export type ViewMode = (typeof VIEW_MODES)[number];

export const DEFAULT_VIEW_MODE: ViewMode = 'standard';

export function isViewMode(value: unknown): value is ViewMode {
  return typeof value === 'string' && (VIEW_MODES as readonly string[]).includes(value);
}

// 시안의 글자 크기 조절 범위(90~120%, 10% 단위)
export const TEXT_SIZE_STEPS = [90, 100, 110, 120] as const;
