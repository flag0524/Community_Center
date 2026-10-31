// Vitest 공통 준비. jsdom에 없는 dialog 동작을 채우고 시험마다 DOM과 저장소를 비운다
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

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
