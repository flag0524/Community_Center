// 화면마다 문서 제목을 '화면 이름 | 조리읍주민자치센터' 형식으로 맞추는 훅
import { useEffect } from 'react';

export const SITE_NAME = '조리읍주민자치센터';

export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} | ${SITE_NAME}`;
  }, [title]);
}
