// 이름·휴대전화로 인증번호를 받아 본인확인을 마치는 공용 폼. 아이디 찾기와 비밀번호 재설정이 함께 쓴다
import { useMutation } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import type { Schemas } from '@jori/api-client';
import { requestOtp, verifyOtp } from '../api/auth';
import { ApiRequestError } from '../api/http';
import { errorMessage } from '../lib/errors';
import { formatPhone } from '../pages/member/JoinFlow';
import { FormMessage } from './FormMessage';
import { TextField } from './TextField';

export interface VerifiedIdentity {
  certRequestId: string;
  code: string;
  name: string;
  phone: string;
  loginId?: string;
}

const PHONE_DIGITS = /^01[0-9]{8,9}$/;
const CODE_FORMAT = /^[0-9]{6}$/;

type Errors = { loginId?: string; name?: string; phone?: string };

export function OtpIdentityForm({
  purpose,
  withLoginId = false,
  onVerified,
}: {
  purpose: Schemas['OtpPurpose'];
  withLoginId?: boolean;
  onVerified: (identity: VerifiedIdentity) => void;
}) {
  const codeRef = useRef<HTMLInputElement>(null);
  const [loginId, setLoginId] = useState('');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [issued, setIssued] = useState<{ certRequestId: string; name: string; phone: string; loginId: string } | null>(null);
  const [errors, setErrors] = useState<Errors>({});
  const [codeError, setCodeError] = useState<string>();
  const [notice, setNotice] = useState({ text: '', error: false });
  const say = (text: string) => setNotice({ text, error: false });
  const fail = (text: string) => setNotice({ text, error: true });

  const issue = useMutation({
    mutationFn: (input: { loginId: string; name: string; digits: string }) =>
      requestOtp(purpose, input.digits, input.name, input.loginId || undefined),
    onSuccess: (result, input) => {
      setIssued({ certRequestId: result.certRequestId, name: input.name, phone: input.digits, loginId: input.loginId });
      setCode('');
      say('인증번호를 문자로 보냈습니다. 5분 안에 입력해 주세요.');
    },
    onError: (error) => fail(errorMessage(error)),
  });

  const verify = useMutation({
    mutationFn: (input: { certRequestId: string; code: string }) => verifyOtp(input.certRequestId, input.code),
    onSuccess: (result, input) => {
      if (result.verified && issued) {
        onVerified({
          certRequestId: input.certRequestId,
          code: input.code,
          name: issued.name,
          phone: issued.phone,
          loginId: issued.loginId || undefined,
        });
        return;
      }
      fail(`인증번호가 올바르지 않습니다. 남은 횟수 ${result.remainingAttempts ?? 0}회`);
      setCode('');
      codeRef.current?.focus();
    },
    onError: (error) => {
      fail(errorMessage(error));
      // 서버가 이 인증 요청을 더는 받지 않는다. 이름·휴대전화 입력부터 다시 하게 한다.
      if (error instanceof ApiRequestError && error.status === 422) setIssued(null);
      setCode('');
    },
  });

  function requestCode(event: FormEvent) {
    event.preventDefault();
    const digits = phone.replace(/[\s-]/g, '');
    const found: Errors = {
      loginId: !withLoginId || loginId.trim() ? undefined : '아이디를 입력해 주세요.',
      name: name.trim() ? undefined : '이름을 입력해 주세요.',
      phone: PHONE_DIGITS.test(digits) ? undefined : '휴대전화 번호를 확인해 주세요. (예: 010-1234-5678)',
    };
    setErrors(found);
    say('');
    if (found.loginId || found.name || found.phone) return;
    issue.mutate({ loginId: loginId.trim(), name: name.trim(), digits });
  }

  function confirmCode(event: FormEvent) {
    event.preventDefault();
    say('');
    if (!CODE_FORMAT.test(code)) {
      setCodeError('인증번호 6자리를 입력해 주세요.');
      return;
    }
    setCodeError(undefined);
    verify.mutate({ certRequestId: issued!.certRequestId, code });
  }

  if (issued === null) {
    return (
      <form className="proto-form" aria-label="인증번호 요청" noValidate onSubmit={requestCode}>
        {withLoginId ? (
          <TextField
            label="아이디"
            name="loginId"
            type="text"
            autoComplete="username"
            value={loginId}
            error={errors.loginId}
            onChange={(event) => setLoginId(event.target.value)}
          />
        ) : null}
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
        <div className="proto-form-actions">
          <button className="button" type="submit" disabled={issue.isPending}>
            인증번호 받기
          </button>
        </div>
        <FormMessage text={notice.text} error={notice.error} />
      </form>
    );
  }

  return (
    <form className="proto-form" aria-label="인증번호 확인" noValidate onSubmit={confirmCode}>
      <dl className="proto-info">
        <div>
          <dt>이름</dt>
          <dd>{issued.name}</dd>
        </div>
        <div>
          <dt>휴대전화</dt>
          <dd>{formatPhone(issued.phone)}</dd>
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
        <button
          className="button secondary"
          type="button"
          disabled={issue.isPending}
          onClick={() => issue.mutate({ loginId: issued.loginId, name: issued.name, digits: issued.phone })}
        >
          인증번호 다시 받기
        </button>
      </div>
      <FormMessage text={notice.text} error={notice.error} />
    </form>
  );
}