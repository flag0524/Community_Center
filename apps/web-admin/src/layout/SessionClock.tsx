// 관리자 세션 남은 시간 표시, 만료 2분 전 연장 안내, 만료 시 로그인으로 보내는 컴포넌트 (RQ-SER-NF-008)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { extendSession } from '../api/auth';
import { ApiRequestError } from '../api/http';
import { sessionQuery } from '../api/queries';
import { formatCountdown, useCountdown } from '../lib/countdown';
import { errorMessage } from '../lib/errors';
import { useExpire } from './useExpire';
import { useLogout } from './useLogout';

const WARNING_SECONDS = 120;

export function SessionClock() {
  const { data: session } = useQuery(sessionQuery);
  if (!session?.authenticated || !session.expiresAt) return null;
  return <Clock expiresAt={session.expiresAt} serverNow={session.serverNow} />;
}

function Clock({ expiresAt, serverNow }: { expiresAt: string; serverNow: string }) {
  const queryClient = useQueryClient();
  const dialog = useRef<HTMLDialogElement>(null);
  const logout = useLogout();

  const expire = useExpire();
  const seconds = useCountdown(expiresAt, serverNow, expire);
  const warning = seconds > 0 && seconds <= WARNING_SECONDS;

  const extend = useMutation({
    mutationFn: extendSession,
    onSuccess: (session) => queryClient.setQueryData(sessionQuery.queryKey, session),
    onError: (error) => {
      if (error instanceof ApiRequestError && error.status === 401) expire();
    },
  });

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (warning && !element.open) element.showModal();
    if (!warning && element.open) element.close();
  }, [warning]);

  return (
    <>
      <small className="adm-session">세션 {formatCountdown(seconds)}</small>
      <dialog
        ref={dialog}
        className="adm-dialog adm-session-dialog"
        aria-labelledby="adm-session-title"
        // 안내를 Esc로 닫으면 연장도 로그아웃도 하지 않은 채 남으므로 두 버튼 중 하나로만 닫는다.
        onCancel={(event) => event.preventDefault()}
      >
        <div className="adm-dialog-head">
          <h2 id="adm-session-title">계속 사용하시겠습니까?</h2>
        </div>
        <div className="adm-dialog-context">
          <p>
            오래 사용하지 않아 <strong>{formatCountdown(seconds)}</strong> 뒤에 자동으로 로그아웃됩니다.
          </p>
          {extend.isError && !(extend.error instanceof ApiRequestError && extend.error.status === 401) && (
            <p className="adm-message error" role="alert">
              {errorMessage(extend.error)}
            </p>
          )}
        </div>
        <div className="adm-dialog-actions">
          <button type="button" className="adm-button secondary" onClick={() => logout.mutate()} disabled={logout.isPending}>
            로그아웃
          </button>
          <button type="button" className="adm-button" onClick={() => extend.mutate()} disabled={extend.isPending}>
            계속 사용
          </button>
        </div>
      </dialog>
    </>
  );
}