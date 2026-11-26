// 화면의 큰 제목이 문서에 나타난 순간 문서 제목도 이미 바뀌어 있는지 확인하는 시험
import { createRoot } from 'react-dom/client';
import { describe, expect, it } from 'vitest';
import { usePageTitle } from './usePageTitle';

function Screen() {
  usePageTitle('아이디 찾기');
  // 느린 검사 서버처럼 그리기가 오래 걸리면 React는 나중 효과(useEffect)를 다음 차례로 미룬다
  const slow = performance.now() + 20;
  while (performance.now() < slow);
  return <h1>아이디 찾기</h1>;
}

describe('usePageTitle', () => {
  it('화면이 그려진 순간에 문서 제목도 맞다', async () => {
    // 자료를 받은 뒤의 갱신처럼 React가 효과를 나중에 처리할 수 있게 act 환경을 잠깐 끈다
    const environment = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
    const before = environment.IS_REACT_ACT_ENVIRONMENT;
    environment.IS_REACT_ACT_ENVIRONMENT = false;
    document.title = '';
    const host = document.body.appendChild(document.createElement('div'));
    const titleWhenShown = new Promise<string>((resolve) => {
      const observer = new MutationObserver(() => {
        if (!host.querySelector('h1')) return;
        observer.disconnect();
        resolve(document.title);
      });
      observer.observe(host, { childList: true, subtree: true });
    });
    const root = createRoot(host);
    try {
      root.render(<Screen />);
      expect(await titleWhenShown).toBe('아이디 찾기 | 조리읍주민자치센터');
    } finally {
      root.unmount();
      host.remove();
      environment.IS_REACT_ACT_ENVIRONMENT = before;
    }
  });
});
