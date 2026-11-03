// 회원탈퇴. 안내를 읽고 비밀번호를 확인한 뒤 한 번 더 확인해 탈퇴한다. 진행 중인 신청·결제·환불이 있으면 서버가 막는다
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { withdraw } from '../../api/member';
import { sessionQuery } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { TextField } from '../../components/TextField';
import { ServicePage } from '../../layout/SubLayout';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '회원탈퇴';
const REASONS: Array<{ value: string; label: string }> = [
  { value: '', label: '선택하지 않음' },
  { value: 'NO_COURSE', label: '이용할 강좌가 없음' },
  { value: 'DIFFICULT', label: '이용이 어려움' },
  { value: 'OTHER', label: '기타' },
];

export function WithdrawPage() {
  usePageTitle(TITLE);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [reason, setReason] = useState('');
  const [password, setPassword] = useState('');
  const [passwordError, setPasswordError] = useState<string>();
  const [confirming, setConfirming] = useState(false);
  const sending = useRef(false);

  const leave = useMutation({
    mutationFn: () =>
      withdraw({ password, reason: reason === '' ? null : (reason as 'NO_COURSE' | 'DIFFICULT' | 'OTHER') }),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ['me'] });
      // 세션이 사라지면 이 화면(로그인 필요)은 로그인으로 돌려보내므로, 로그인이 필요 없는 완료 화면으로 먼저 옮긴다.
      navigate('/withdraw/done', { replace: true });
      void queryClient.invalidateQueries({ queryKey: sessionQuery.queryKey });
    },
    onError: () => setConfirming(false),
    onSettled: () => {
      sending.current = false;
    },
  });

  function ask(event: FormEvent) {
    event.preventDefault();
    if (!password) {
      setPasswordError('비밀번호를 입력해 주세요.');
      return;
    }
    setPasswordError(undefined);
    leave.reset();
    setConfirming(true);
  }

  function send() {
    if (sending.current) return;
    sending.current = true;
    leave.mutate();
  }

  const server = fieldErrors(leave.error);
  const message = leave.isError && !server.password ? errorMessage(leave.error) : '';

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: '회원정보수정', to: '/me/profile' }, { label: TITLE }]}>
      <div className="proto">
          <>
            <h2>회원탈퇴 안내</h2>
            <p>진행 중인 수강신청·결제·환불 내역을 먼저 확인해 주세요.</p>
            <form className="proto-form" aria-label="회원탈퇴" noValidate onSubmit={ask}>
              <label className="field">
                탈퇴 사유 (선택)
                <select value={reason} onChange={(event) => setReason(event.target.value)}>
                  {REASONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <TextField
                label="비밀번호 확인"
                name="password"
                type="password"
                autoComplete="current-password"
                maxLength={64}
                value={password}
                error={passwordError ?? server.password}
                onChange={(event) => setPassword(event.target.value)}
              />
              {confirming ? (
                <div className="proto-consent" role="group" aria-label="회원탈퇴 확인">
                  <p>탈퇴하면 30일 뒤 개인정보가 파기되며 되돌릴 수 없습니다. 탈퇴할까요?</p>
                  <div className="proto-actions">
                    <button className="button" type="button" disabled={leave.isPending} onClick={send}>
                      탈퇴하기
                    </button>
                    <button className="button secondary" type="button" onClick={() => setConfirming(false)}>
                      돌아가기
                    </button>
                  </div>
                </div>
              ) : (
                <div className="proto-form-actions">
                  <button className="button" type="submit">
                    회원탈퇴
                  </button>
                </div>
              )}
              <FormMessage text={message} error />
            </form>
          </>
      </div>
    </ServicePage>
  );
}