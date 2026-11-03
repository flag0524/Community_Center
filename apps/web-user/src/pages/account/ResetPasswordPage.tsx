// 비밀번호 재설정. 아이디·이름·휴대전화 본인확인 뒤 새 비밀번호를 정한다. 성공하면 기존 세션이 모두 끊긴다(FN-062)
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { resetPassword } from '../../api/auth';
import { sessionQuery } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { OtpIdentityForm, type VerifiedIdentity } from '../../components/OtpIdentityForm';
import { TextField } from '../../components/TextField';
import { ServicePage } from '../../layout/SubLayout';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '비밀번호 재설정';
const PASSWORD_MIN = 10;
const PASSWORD_MAX = 64;

export function ResetPasswordPage() {
  usePageTitle(TITLE);
  const queryClient = useQueryClient();
  const [identity, setIdentity] = useState<VerifiedIdentity | null>(null);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>({});
  const [done, setDone] = useState(false);

  const reset = useMutation({
    mutationFn: (verified: VerifiedIdentity) =>
      resetPassword({
        certRequestId: verified.certRequestId,
        code: verified.code,
        loginId: verified.loginId ?? '',
        newPassword: password,
      }),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: ['me'] });
      await queryClient.invalidateQueries({ queryKey: sessionQuery.queryKey });
      setDone(true);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const found = {
      password:
        password.length >= PASSWORD_MIN && password.length <= PASSWORD_MAX
          ? undefined
          : `${PASSWORD_MIN}자 이상 ${PASSWORD_MAX}자 이하로 입력해 주세요.`,
      confirm: confirm === password ? undefined : '비밀번호가 서로 다릅니다.',
    };
    setErrors(found);
    if (found.password || found.confirm || !identity) return;
    reset.mutate(identity);
  }

  const serverFields = fieldErrors(reset.error);
  const message = reset.isError ? (Object.values(serverFields)[0] ?? errorMessage(reset.error)) : '';

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '회원서비스' }, { label: TITLE }]}>
      <div className="proto">
        {done ? (
          <>
            <div className="proto-result" role="status">
              <h2>비밀번호가 변경되었습니다.</h2>
              <p>새 비밀번호로 로그인해 주세요. 다른 기기의 로그인은 모두 해제되었습니다.</p>
            </div>
            <div className="proto-actions">
              <Link className="button" to="/login">
                로그인
              </Link>
            </div>
          </>
        ) : identity === null ? (
          <OtpIdentityForm purpose="PASSWORD_RESET" withLoginId onVerified={setIdentity} />
        ) : (
          <form className="proto-form" aria-label="새 비밀번호 설정" noValidate onSubmit={submit}>
            <TextField
              label="새 비밀번호"
              name="newPassword"
              type="password"
              autoComplete="new-password"
              maxLength={PASSWORD_MAX}
              value={password}
              error={errors.password}
              hint={`비밀번호는 ${PASSWORD_MIN}자 이상으로 입력해 주세요.`}
              onChange={(event) => setPassword(event.target.value)}
            />
            <TextField
              label="새 비밀번호 확인"
              name="passwordConfirm"
              type="password"
              autoComplete="new-password"
              maxLength={PASSWORD_MAX}
              value={confirm}
              error={errors.confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
            <div className="proto-form-actions">
              <button className="button" type="submit" disabled={reset.isPending}>
                변경
              </button>
            </div>
            <FormMessage text={message} error />
          </form>
        )}
      </div>
    </ServicePage>
  );
}