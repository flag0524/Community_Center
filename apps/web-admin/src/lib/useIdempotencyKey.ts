// 버튼을 누른 한 번의 시도마다 같은 멱등키를 쓰게 하는 훅. 성공하면 새 키로 바꾼다
import { useRef } from 'react';

const newKey = () => crypto.randomUUID().replaceAll('-', '');

export function useIdempotencyKey() {
  const key = useRef(newKey());
  return { current: () => key.current, renew: () => (key.current = newKey()) };
}