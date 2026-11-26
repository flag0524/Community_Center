// 화면마다 문서 제목을 '화면 이름 | 조리읍주민자치센터' 형식으로 맞추는 훅
import { useLayoutEffect } from 'react';

export const SITE_NAME = '조리읍주민자치센터';

export function usePageTitle(title: string): void {
  // 화면이 바뀌는 그 순간에 제목도 바꾼다. useEffect는 그리기가 오래 걸리면 제목이 한 박자 늦는다
  useLayoutEffect(() => {
    document.title = `${title} | ${SITE_NAME}`;
  }, [title]);
}
