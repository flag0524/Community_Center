// 화면 모드와 글자 크기를 앱 전체에 나눠 주고 html 속성과 세션 저장소에 반영하는 Provider
import type { ViewMode } from '@jori/ui';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  TEXT_SIZE_STORAGE_KEY,
  VIEW_STORAGE_KEY,
  canStep,
  parseTextSize,
  readStorage,
  resolveViewMode,
  rootFontSizePercent,
  stepTextSize,
  type TextSize,
} from './viewMode';

interface ViewModeValue {
  view: ViewMode;
  textSize: TextSize;
  changeTextSize: (step: -10 | 0 | 10) => void;
  canChangeTextSize: (step: -10 | 10) => boolean;
}

const ViewModeContext = createContext<ViewModeValue | null>(null);

function session(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function writeSession(key: string, value: string): void {
  try {
    session()?.setItem(key, value);
  } catch {
    // 저장이 막혀도 현재 화면에서는 값이 유지된다.
  }
}

export function ViewModeProvider({ children }: { children: ReactNode }) {
  const [searchParams] = useSearchParams();
  const urlView = searchParams.get('view');
  const [view, setView] = useState<ViewMode>(() => resolveViewMode(window.location.search, session()));
  const [textSize, setTextSize] = useState<TextSize>(() =>
    parseTextSize(readStorage(session(), TEXT_SIZE_STORAGE_KEY)),
  );

  // 주소의 view 값이 바뀌면 따라간다. 화면 선택 링크가 이 값을 바꾼다.
  useEffect(() => {
    if (urlView === 'easy' || urlView === 'standard') setView(urlView);
  }, [urlView]);

  useEffect(() => {
    document.documentElement.dataset.view = view;
    writeSession(VIEW_STORAGE_KEY, view);
  }, [view]);

  useEffect(() => {
    document.documentElement.style.fontSize = `${rootFontSizePercent(textSize, view)}%`;
    writeSession(TEXT_SIZE_STORAGE_KEY, String(textSize));
  }, [textSize, view]);

  const changeTextSize = useCallback((step: -10 | 0 | 10) => {
    setTextSize((current) => stepTextSize(current, step));
  }, []);

  const canChangeTextSize = useCallback((step: -10 | 10) => canStep(textSize, step), [textSize]);

  const value = useMemo(
    () => ({ view, textSize, changeTextSize, canChangeTextSize }),
    [view, textSize, changeTextSize, canChangeTextSize],
  );

  return <ViewModeContext.Provider value={value}>{children}</ViewModeContext.Provider>;
}

export function useViewMode(): ViewModeValue {
  const value = useContext(ViewModeContext);
  if (!value) throw new Error('ViewModeProvider 안에서만 쓸 수 있습니다.');
  return value;
}
