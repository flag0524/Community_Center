// 비밀번호 변경. 현재 비밀번호를 확인하고 새 비밀번호로 바꾼다. 이 기기의 로그인은 유지된다
import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { changePassword } from '../../api/member';
import { FormMessage } from '../../components/FormMessage';
import { TextField } from '../../components/TextField';
import { ServicePage } from '../../layout/SubLayout';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '비밀번호 변경';
const PASSWORD_MIN = 10;
const PASSWORD_MAX = 64;

export function ChangePasswordPage() {
  usePageTitle(TITLE);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<{ current?: string; next?: string; confirm?: string }>({});
  const [changed, setChanged] = useState(false);

  const change = useMutation({
    mutationFn: () => changePassword({ currentPassword: current, newPassword: next }),
    onSuccess: () => {
      setCurrent('');
      setNext('');
      setConfirm('');
      setChanged(true);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setChanged(false);
    const found = {
      current: current ? undefined : '현재 비밀번호를 입력해 주세요.',
      next:
        next.length >= PASSWORD_MIN && next.length <= PASSWORD_MAX
          ? undefined
          : `${PASSWORD_MIN}자 이상 ${PASSWORD_MAX}자 이하로 입력해 주세요.`,
      confirm: confirm === next ? undefined : '비밀번호가 서로 다릅니다.',
    };
    setErrors(found);
    if (found.current || found.next || found.confirm) return;
    change.mutate();
  }

  const server = fieldErrors(change.error);
  const message = changed ? '비밀번호가 변경되었습니다.' : change.isError && Object.keys(server).length === 0 ? errorMessage(change.error) : '';

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: '회원정보수정', to: '/me/profile' }, { label: TITLE }]}>
      <div className="proto">
        <form className="proto-form" aria-label="비밀번호 변경" noValidate onSubmit={submit}>
          <TextField
            label="현재 비밀번호"
            name="currentPassword"
            type="password"
            autoComplete="current-password"
            maxLength={PASSWORD_MAX}
            value={current}
            error={errors.current ?? server.currentPassword}
            onChange={(event) => setCurrent(event.target.value)}
          />
          <TextField
            label="새 비밀번호"
            name="newPassword"
            type="password"
            autoComplete="new-password"
            maxLength={PASSWORD_MAX}
            value={next}
            error={errors.next ?? server.newPassword}
            hint={`비밀번호는 ${PASSWORD_MIN}자 이상으로 입력해 주세요.`}
            onChange={(event) => setNext(event.target.value)}
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
            <button className="button" type="submit" disabled={change.isPending}>
              변경
            </button>
          </div>
          <FormMessage text={message} error={!changed && change.isError} />
        </form>
        <div className="proto-actions">
          <Link className="button secondary" to="/me/profile">
            회원정보
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}