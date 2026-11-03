// 아이디·비밀번호 로그인. 성공하면 next 주소나 홈으로 보내고 이미 로그인한 사람은 바로 돌려보낸다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { login } from '../../api/auth';
import { sessionQuery } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { TextField } from '../../components/TextField';
import { ServicePage } from '../../layout/SubLayout';
import { errorMessage } from '../../lib/errors';
import { safeNext } from '../../lib/safeNext';
import { usePageTitle } from '../../lib/usePageTitle';

export function LoginPage() {
  usePageTitle('로그인');
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const next = safeNext(searchParams.get('next'));
  const session = useQuery(sessionQuery);
  const passwordRef = useRef<HTMLInputElement>(null);
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ loginId?: string; password?: string }>({});
  const [message, setMessage] = useState('');

  const mutation = useMutation({
    mutationFn: login,
    // 세션이 바뀌면 아래 Navigate가 next 주소로 보낸다.
    onSuccess: (info) => {
      // 앞에 남은 다른 회원의 신청·결제 정보가 보이지 않게 회원 전용 캐시를 먼저 지운다.
      queryClient.removeQueries({ queryKey: ['me'] });
      queryClient.setQueryData(sessionQuery.queryKey, info);
    },
    onError: (error) => {
      setMessage(errorMessage(error));
      setPassword('');
      passwordRef.current?.focus();
    },
  });

  if (session.data?.authenticated) return <Navigate to={next} replace />;

  function submit(event: FormEvent) {
    event.preventDefault();
    const id = loginId.trim();
    const found = {
      loginId: id ? undefined : '아이디를 입력해 주세요.',
      password: password ? undefined : '비밀번호를 입력해 주세요.',
    };
    setErrors(found);
    setMessage('');
    if (found.loginId || found.password) return;
    mutation.mutate({ loginId: id, password });
  }

  return (
    <ServicePage title="로그인" crumbs={[{ label: '회원서비스' }, { label: '로그인' }]}>
      <div className="proto">
        <div className="proto-login">
          <form className="proto-form" aria-label="로그인" noValidate onSubmit={submit}>
            <TextField
              label="아이디"
              name="loginId"
              type="text"
              autoComplete="username"
              value={loginId}
              error={errors.loginId}
              onChange={(event) => setLoginId(event.target.value)}
            />
            <TextField
              label="비밀번호"
              name="password"
              type="password"
              autoComplete="current-password"
              inputRef={passwordRef}
              value={password}
              error={errors.password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <div className="proto-form-actions">
              <button className="button" type="submit" disabled={mutation.isPending}>
                로그인
              </button>
            </div>
            <FormMessage text={message} error />
          </form>
          <nav className="proto-account-links" aria-label="계정 안내">
            <Link to="/join">회원가입</Link>
            <Link to="/find-id">아이디 찾기</Link>
            <Link to="/reset-password">비밀번호 찾기</Link>
          </nav>
        </div>
      </div>
    </ServicePage>
  );
}
