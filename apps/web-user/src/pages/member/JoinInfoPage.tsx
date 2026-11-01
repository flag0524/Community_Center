// 회원가입 3단계. 아이디·비밀번호·이메일을 입력해 가입을 요청한다
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { checkLoginId, join } from '../../api/auth';
import { ApiRequestError } from '../../api/http';
import { termQuery, type TermType } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { TextField } from '../../components/TextField';
import { ServicePage } from '../../layout/SubLayout';
import { errorMessage } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';
import { formatPhone, useJoinFlow } from './JoinFlow';

const TITLE = '회원가입 · 정보입력';
const EMAIL_FORMAT = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PASSWORD_MIN = 10;
const PASSWORD_MAX = 64;
const PASSWORD_HINT = `비밀번호는 ${PASSWORD_MIN}자 이상으로 입력해 주세요.`;

type Errors = Partial<Record<'loginId' | 'password' | 'confirm' | 'email', string>>;
// 서버가 필드 이름으로 돌려주는 검증 오류를 같은 이름의 입력 칸에 붙인다.
const SERVER_FIELDS = ['loginId', 'password', 'email'] as const;

const AGREEMENT_TYPES: TermType[] = ['TERMS_OF_USE', 'PRIVACY_CONSENT', 'MARKETING_CONSENT'];

export function JoinInfoPage() {
  usePageTitle(TITLE);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { draft, update } = useJoinFlow();
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [email, setEmail] = useState('');
  const [marketing, setMarketing] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [idResult, setIdResult] = useState<'available' | 'taken' | null>(null);
  const [message, setMessage] = useState('');

  const idCheck = useMutation({
    mutationFn: checkLoginId,
    onSuccess: (result) => setIdResult(result.available ? 'available' : 'taken'),
    onError: (error) => setMessage(errorMessage(error)),
  });

  const submitJoin = useMutation({
    mutationFn: async () => {
      // 동의한 약관의 버전을 서버 문서에서 읽어 가입 요청에 함께 보낸다.
      const terms = await Promise.all(AGREEMENT_TYPES.map((type) => queryClient.fetchQuery(termQuery(type))));
      return join({
        certRequestId: draft.certRequestId!,
        code: draft.code,
        loginId: loginId.trim(),
        password,
        email: email.trim(),
        agreements: terms.map((term) => ({
          termType: term.termType,
          version: term.version,
          agreed: term.termType !== 'MARKETING_CONSENT' || marketing,
        })),
      });
    },
    onSuccess: () => navigate('/join/complete'),
    onError: (error) => {
      setMessage(errorMessage(error));
      if (!(error instanceof ApiRequestError)) return;
      if (error.body?.code === 'OTP_INVALID' || error.body?.code === 'OTP_EXPIRED') {
        // 본인확인이 더는 유효하지 않다. 다시 받게 한다.
        update({ certRequestId: null, verified: false, code: '' });
        navigate('/join/verify');
        return;
      }
      const fromServer: Errors = {};
      for (const field of SERVER_FIELDS) {
        const text = error.body?.fields?.[field];
        if (text) fromServer[field] = text;
      }
      if (error.body?.code === 'JOIN_LOGIN_ID_TAKEN') fromServer.loginId ??= error.body.message;
      setErrors(fromServer);
    },
  });

  if (!draft.agreed) return <Navigate to="/join" replace />;
  if (!draft.verified) return <Navigate to="/join/verify" replace />;

  function changeLoginId(value: string) {
    setLoginId(value);
    setIdResult(null);
  }

  function checkId() {
    const id = loginId.trim();
    setMessage('');
    if (!id) {
      setErrors({ loginId: '아이디를 입력해 주세요.' });
      return;
    }
    setErrors({});
    idCheck.mutate(id);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const found: Errors = {
      loginId: loginId.trim() ? undefined : '아이디를 입력해 주세요.',
      password:
        password.length >= PASSWORD_MIN && password.length <= PASSWORD_MAX
          ? undefined
          : `${PASSWORD_MIN}자 이상 ${PASSWORD_MAX}자 이하로 입력해 주세요.`,
      confirm: confirm === password ? undefined : '비밀번호가 서로 다릅니다.',
      email: EMAIL_FORMAT.test(email.trim()) ? undefined : '이메일 주소 형식을 확인해 주세요.',
    };
    setErrors(found);
    setMessage('');
    if (Object.values(found).some(Boolean)) return;
    submitJoin.mutate();
  }

  const idError = errors.loginId ?? (idResult === 'taken' ? '이미 사용 중인 아이디입니다.' : undefined);

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '회원서비스' }, { label: TITLE }]}>
      <div className="proto">
        <h2>회원정보</h2>
        <form className="proto-form" aria-label="회원정보" noValidate onSubmit={submit}>
          <dl className="proto-info">
            <div>
              <dt>이름</dt>
              <dd>{draft.name}</dd>
            </div>
            <div>
              <dt>휴대전화</dt>
              <dd>{formatPhone(draft.phone)}</dd>
            </div>
          </dl>
          <div className="field-with-action">
            <TextField
              label="아이디"
              name="loginId"
              type="text"
              autoComplete="username"
              maxLength={64}
              value={loginId}
              error={idError}
              hint={idResult === 'available' ? '사용할 수 있는 아이디입니다.' : undefined}
              onChange={(event) => changeLoginId(event.target.value)}
            />
            <button className="button secondary" type="button" disabled={idCheck.isPending} onClick={checkId}>
              중복확인
            </button>
          </div>
          <TextField
            label="비밀번호"
            name="password"
            type="password"
            autoComplete="new-password"
            maxLength={PASSWORD_MAX}
            value={password}
            error={errors.password}
            hint={PASSWORD_HINT}
            onChange={(event) => setPassword(event.target.value)}
          />
          <TextField
            label="비밀번호 확인"
            name="passwordConfirm"
            type="password"
            autoComplete="new-password"
            maxLength={PASSWORD_MAX}
            value={confirm}
            error={errors.confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
          <TextField
            label="이메일"
            name="email"
            type="email"
            autoComplete="email"
            maxLength={254}
            value={email}
            error={errors.email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <label className="proto-check">
            <input type="checkbox" checked={marketing} onChange={(event) => setMarketing(event.target.checked)} /> 센터
            소식 수신에 동의합니다. (선택)
          </label>
          <div className="proto-form-actions">
            <button className="button" type="submit" disabled={submitJoin.isPending}>
              회원가입
            </button>
          </div>
          <FormMessage text={message} error />
        </form>
      </div>
    </ServicePage>
  );
}
