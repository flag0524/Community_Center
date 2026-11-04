// 결제기한 카운트다운. 기기 시계가 아니라 서버가 준 시각을 기준으로 줄어든다
import { useEffect, useRef, useState } from 'react';

/** 응답을 받은 뒤 elapsedMs가 흘렀을 때 남은 초. 서버 시각 기준이라 기기 시계가 틀려도 같다. */
export function remainingSeconds(deadline: string, serverNow: string, elapsedMs: number): number {
  const leftMs = new Date(deadline).getTime() - (new Date(serverNow).getTime() + elapsedMs);
  return Math.max(0, Math.ceil(leftMs / 1000));
}

/** 599 → 09:59 */
export function formatCountdown(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

/** 1초마다 남은 초를 갱신하고, 0이 되면 onZero를 한 번 부른다. 상태 판정은 서버가 하므로 화면은 알리기만 한다. */
export function useCountdown(deadline: string, serverNow: string, onZero: () => void): number {
  const startedAt = useRef(Date.now());
  const notified = useRef(false);
  const onZeroRef = useRef(onZero);
  onZeroRef.current = onZero;
  const [seconds, setSeconds] = useState(() => remainingSeconds(deadline, serverNow, 0));

  useEffect(() => {
    startedAt.current = Date.now();
    notified.current = false;
    const tick = () => {
      const left = remainingSeconds(deadline, serverNow, Date.now() - startedAt.current);
      setSeconds(left);
      if (left === 0 && !notified.current) {
        notified.current = true;
        onZeroRef.current();
      }
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [deadline, serverNow]);

  return seconds;
}
