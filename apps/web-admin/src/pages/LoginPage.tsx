// 관리자 로그인 화면. 아이디·비밀번호만 받고 MFA는 쓰지 않는다 (ADM-LGN-001)
import logo from '@jori/ui/assets/paju-ci.jpg';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { login } from '../api/auth';
import { sessionQuery } from '../api/queries';
import { errorMessage, fieldErrors } from '../lib/errors';
import { safeNext } from '../lib/safeNext';

export function LoginPage() {
  const [params] = useSearchParams();
  const next = safeNext(params.get('next'));
  const queryClient = useQueryClient();
  const { data: session } = useQuery(sessionQuery);
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [missing, setMissing] = useState<{ loginId?: string; password?: string }>({});

  // 로그인 화면만 배경과 카드 배치가 다르다. 시안이 body 클래스로 구분한다.
  useEffect(() => {
    document.body.classList.add('adm-login-page');
    return () => document.body.classList.remove('adm-login-page');
  }, []);

  const mutation = useMutation({
    mutationFn: login,
    onSuccess: (result) => queryClient.setQueryData(sessionQuery.queryKey, result),
  });

  if (session?.authenticated) return <Navigate to={next} replace />;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors = {
      loginId: loginId.trim() ? undefined : '아이디를 입력해 주세요.',
      password: password ? undefined : '비밀번호를 입력해 주세요.',
    };
    setMissing(errors);
    if (errors.loginId || errors.password) return;
    mutation.mutate({ loginId: loginId.trim(), password });
  };

  const serverFields = fieldErrors(mutation.error);

  return (
    <main className="adm-login-card">
      <div className="adm-brand">
        <img src={logo} alt="파주시" />
        <div className="adm-brand-title">
          <strong>조리읍</strong>
          <span>주민자치센터</span>
        </div>
      </div>
      <h1>관리자 로그인</h1>
      {params.get('expired') === '1' && (
        <p className="adm-message" role="status">
          오래 사용하지 않아 로그아웃되었습니다. 다시 로그인해 주세요.
        </p>
      )}
      <form aria-label="관리자 로그인" noValidate onSubmit={submit}>
        <label>
          아이디
          <input
            name="loginId"
            autoComplete="username"
            value={loginId}
            onChange={(event) => setLoginId(event.target.value)}
            aria-invalid={Boolean(missing.loginId ?? serverFields.loginId) || undefined}
            aria-describedby={missing.loginId ? 'login-id-error' : undefined}
          />
        </label>
        {missing.loginId && (
          <p className="adm-message error" id="login-id-error">
            {missing.loginId}
          </p>
        )}
        <label>
          비밀번호
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={Boolean(missing.password ?? serverFields.password) || undefined}
            aria-describedby={missing.password ? 'login-password-error' : undefined}
          />
        </label>
        {missing.password && (
          <p className="adm-message error" id="login-password-error">
            {missing.password}
          </p>
        )}
        {mutation.isError && (
          <p className="adm-message error" role="alert">
            {errorMessage(mutation.error)}
          </p>
        )}
        <button className="adm-button" type="submit" disabled={mutation.isPending}>
          로그인
        </button>
      </form>
    </main>
  );
}