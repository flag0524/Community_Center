// 회원가입 2단계. 이름·휴대전화로 인증번호를 받고, 받은 6자리를 입력해 본인확인을 마친다
import { useMutation } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { requestJoinOtp, verifyOtp } from '../../api/auth';
import { ApiRequestError } from '../../api/http';
import { FormMessage } from '../../components/FormMessage';
import { TextField } from '../../components/TextField';
import { ServicePage } from '../../layout/SubLayout';
import { errorMessage } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';
import { formatPhone, useJoinFlow } from './JoinFlow';

const TITLE = '회원가입 · 본인확인';
const PHONE_DIGITS = /^01[0-9]{8,9}$/;
const CODE_FORMAT = /^[0-9]{6}$/;

type RequestErrors = { name?: string; phone?: string; consent?: string };

export function JoinVerifyPage() {
  usePageTitle(TITLE);
  const navigate = useNavigate();
  const { draft, update } = useJoinFlow();
  const codeRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(draft.name);
  const [phone, setPhone] = useState(draft.phone ? formatPhone(draft.phone) : '');
  const [consent, setConsent] = useState(false);
  const [code, setCode] = useState('');
  const [errors, setErrors] = useState<RequestErrors>({});
  const [codeError, setCodeError] = useState<string>();
  const [notice, setNotice] = useState({ text: '', error: false });
  const say = (text: string) => setNotice({ text, error: false });
  const fail = (text: string) => setNotice({ text, error: true });

  const issue = useMutation({
    mutationFn: (input: { name: string; digits: string }) => requestJoinOtp(input.digits, input.name),
    onSuccess: (issued, input) => {
      update({ name: input.name, phone: input.digits, certRequestId: issued.certRequestId, verified: false, code: '' });
      setCode('');
      say('인증번호를 문자로 보냈습니다. 5분 안에 입력해 주세요.');
    },
    onError: (error) => fail(errorMessage(error)),
  });

  const verify = useMutation({
    mutationFn: (input: { certRequestId: string; code: string }) => verifyOtp(input.certRequestId, input.code),
    onSuccess: (result, input) => {
      if (result.verified) {
        update({ verified: true, code: input.code });
        navigate('/join/info');
        return;
      }
      fail(`인증번호가 올바르지 않습니다. 남은 횟수 ${result.remainingAttempts ?? 0}회`);
      setCode('');
      codeRef.current?.focus();
    },
    onError: (error) => {
      fail(errorMessage(error));
      // 서버가 이 인증 요청을 더는 받지 않는다. 이름·휴대전화 입력부터 다시 하게 한다.
      if (error instanceof ApiRequestError && error.status === 422) update({ certRequestId: null, code: '' });
      setCode('');
    },
  });

  if (!draft.agreed) return <Navigate to="/join" replace />;

  function requestCode(event: FormEvent) {
    event.preventDefault();
    const digits = phone.replace(/[\s-]/g, '');
    const found: RequestErrors = {
      name: name.trim() ? undefined : '이름을 입력해 주세요.',
      phone: PHONE_DIGITS.test(digits) ? undefined : '휴대전화 번호를 확인해 주세요. (예: 010-1234-5678)',
      consent: consent ? undefined : '본인확인 진행에 동의해 주세요.',
    };
    setErrors(found);
    say('');
    if (found.name || found.phone || found.consent) return;
    issue.mutate({ name: name.trim(), digits });
  }

  function resend() {
    say('');
    issue.mutate({ name: draft.name, digits: draft.phone });
  }

  function confirmCode(event: FormEvent) {
    event.preventDefault();
    say('');
    if (!CODE_FORMAT.test(code)) {
      setCodeError('인증번호 6자리를 입력해 주세요.');
      return;
    }
    setCodeError(undefined);
    verify.mutate({ certRequestId: draft.certRequestId!, code });
  }

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '회원서비스' }, { label: TITLE }]}>
      <div className="proto">
        <h2>휴대전화 본인확인</h2>
        <p>회원가입을 위해 본인확인을 진행합니다.</p>
        {draft.certRequestId === null ? (
          <form className="proto-form" aria-label="인증번호 요청" noValidate onSubmit={requestCode}>
            <TextField
              label="이름"
              name="name"
              type="text"
              autoComplete="name"
              maxLength={50}
              value={name}
              error={errors.name}
              onChange={(event) => setName(event.target.value)}
            />
            <TextField
              label="휴대전화"
              name="phone"
              type="tel"
              autoComplete="tel"
              inputMode="tel"
              value={phone}
              error={errors.phone}
              onChange={(event) => setPhone(event.target.value)}
            />
            <label className="proto-check">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> 본인확인 진행에
              동의합니다.
            </label>
            {errors.consent ? <p className="field-error">{errors.consent}</p> : null}
            <div className="proto-form-actions">
              <button className="button" type="submit" disabled={issue.isPending}>
                인증번호 받기
              </button>
            </div>
            <FormMessage text={notice.text} error={notice.error} />
          </form>
        ) : (
          <form className="proto-form" aria-label="인증번호 확인" noValidate onSubmit={confirmCode}>
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
            <TextField
              label="인증번호"
              name="code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              inputRef={codeRef}
              value={code}
              error={codeError}
              onChange={(event) => setCode(event.target.value)}
            />
            <div className="proto-form-actions">
              <button className="button" type="submit" disabled={verify.isPending}>
                본인확인
              </button>{' '}
              <button className="button secondary" type="button" disabled={issue.isPending} onClick={resend}>
                인증번호 다시 받기
              </button>
            </div>
            <FormMessage text={notice.text} error={notice.error} />
          </form>
        )}
      </div>
    </ServicePage>
  );
}
