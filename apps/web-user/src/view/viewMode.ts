// 기본 화면과 쉬운 화면 선택, 글자 크기 계산처럼 DOM에 닿지 않는 순수 규칙
import { DEFAULT_VIEW_MODE, TEXT_SIZE_STEPS, isViewMode, type ViewMode } from '@jori/ui';

export const VIEW_STORAGE_KEY = 'view';
export const TEXT_SIZE_STORAGE_KEY = 'text-size';

type ReadableStorage = Pick<Storage, 'getItem'>;

export function readStorage(storage: ReadableStorage | null, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    // 저장소가 막힌 브라우저(사생활 보호 모드 등)에서는 저장 없이 동작한다.
    return null;
  }
}

/** public/view-mode.js와 같은 규칙. 주소의 view 값이 우선이고 없으면 세션에 기억한 값을 쓴다. */
export function resolveViewMode(search: string, storage: ReadableStorage | null): ViewMode {
  const fromUrl = new URLSearchParams(search).get('view');
  if (isViewMode(fromUrl)) return fromUrl;
  const fromStorage = readStorage(storage, VIEW_STORAGE_KEY);
  return isViewMode(fromStorage) ? fromStorage : DEFAULT_VIEW_MODE;
}

export type TextSize = (typeof TEXT_SIZE_STEPS)[number];

export const DEFAULT_TEXT_SIZE: TextSize = 100;
const MIN_TEXT_SIZE = TEXT_SIZE_STEPS[0];
const MAX_TEXT_SIZE = TEXT_SIZE_STEPS[TEXT_SIZE_STEPS.length - 1] as TextSize;

export function parseTextSize(value: string | null): TextSize {
  const parsed = Number(value);
  return (TEXT_SIZE_STEPS as readonly number[]).includes(parsed) ? (parsed as TextSize) : DEFAULT_TEXT_SIZE;
}

/** step이 0이면 기본 크기로 되돌리고, 아니면 범위 안에서 한 단계 움직인다. */
export function stepTextSize(current: TextSize, step: -10 | 0 | 10): TextSize {
  if (step === 0) return DEFAULT_TEXT_SIZE;
  const next = Math.max(MIN_TEXT_SIZE, Math.min(MAX_TEXT_SIZE, current + step));
  return next as TextSize;
}

export function canStep(current: TextSize, step: -10 | 10): boolean {
  return step === -10 ? current > MIN_TEXT_SIZE : current < MAX_TEXT_SIZE;
}

/** 쉬운 화면은 기본 글자를 25% 키운 상태에서 사용자 조절을 곱한다. */
export function rootFontSizePercent(size: TextSize, view: ViewMode): number {
  return size * (view === 'easy' ? 1.25 : 1);
}
