// Vitest 공통 준비. jsdom에 없는 dialog 동작을 채우고 시험마다 DOM과 저장소를 비운다
import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';

// findBy·waitFor의 기본 대기는 1초다. 부하가 큰 검증 환경에서도 느린 렌더로 거짓 실패가 나지 않게 늘린다.
// 요소가 정말 없을 때만 이 시간을 다 쓰므로 정상 실행 속도에는 영향이 없다.
configure({ asyncUtilTimeout: 5000 });

// jsdom은 dialog.showModal/close를 구현하지 않아 open 속성만 바꾸는 대체 구현을 둔다.
HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
  this.setAttribute('open', '');
};
HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
  this.removeAttribute('open');
  this.dispatchEvent(new Event('close'));
};

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  document.documentElement.removeAttribute('data-view');
  document.documentElement.style.fontSize = '';
});
