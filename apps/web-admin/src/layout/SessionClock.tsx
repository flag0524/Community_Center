// 관리자 세션 남은 시간 표시, 만료 2분 전 연장 안내, 만료 시 로그인으로 보내는 컴포넌트 (RQ-SER-NF-008)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { extendSession, readSession } from '../api/auth';
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
  // 업무 요청은 서버의 유휴 만료를 늘리지만 화면이 받은 시각은 그대로다. 안내하거나 내보내기 전에 서버에 다시 묻는다.
  const sync = async () => {
    const latest = await readSession();
    if (latest.authenticated) queryClient.setQueryData(sessionQuery.queryKey, latest);
    else expire();
  };
  const seconds = useCountdown(expiresAt, serverNow, () => void sync().catch(expire));
  const warning = seconds > 0 && seconds <= WARNING_SECONDS;
  const [checked, setChecked] = useState<string | null>(null); // 서버에 확인을 마친 만료 시각
  const confirmed = warning && checked === expiresAt;

  useEffect(() => {
    if (!warning || checked === expiresAt) return;
    // 확인하지 못해도 안내는 띄운다. 연장하거나 로그아웃할 기회를 잃지 않게 한다.
    void sync()
      .catch(() => undefined)
      .finally(() => setChecked(expiresAt));
    // sync는 렌더마다 새로 만들어지므로 의존성에 넣지 않는다. 만료 시각마다 한 번만 확인한다.
  }, [warning, expiresAt, checked]);

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
    if (confirmed && !element.open) element.showModal();
    if (!confirmed && element.open) element.close();
  }, [confirmed]);

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