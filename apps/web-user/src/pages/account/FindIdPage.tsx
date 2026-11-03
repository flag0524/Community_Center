// 아이디 찾기. 이름·휴대전화 본인확인 뒤 앞 2글자만 보이는 아이디를 알려 준다(FN-061)
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { findId } from '../../api/auth';
import { FormMessage } from '../../components/FormMessage';
import { OtpIdentityForm } from '../../components/OtpIdentityForm';
import { ServicePage } from '../../layout/SubLayout';
import { errorMessage } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '아이디 찾기';

export function FindIdPage() {
  usePageTitle(TITLE);
  const [result, setResult] = useState<{ masked: string | null } | null>(null);
  const lookup = useMutation({
    mutationFn: (input: { certRequestId: string; code: string }) => findId(input.certRequestId, input.code),
    onSuccess: (data) => setResult({ masked: data.maskedLoginId ?? null }),
  });

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '회원서비스' }, { label: TITLE }]}>
      <div className="proto">
        {result === null ? (
          <>
            <h2>본인확인</h2>
            <OtpIdentityForm purpose="ID_FIND" onVerified={(identity) => lookup.mutate(identity)} />
            <FormMessage text={lookup.isError ? errorMessage(lookup.error) : ''} error />
          </>
        ) : result.masked ? (
          <>
            <div className="proto-result">
              <h3>가입한 아이디</h3>
              <p>
                <strong>{result.masked}</strong>
              </p>
            </div>
            <div className="proto-actions">
              <Link className="button" to="/reset-password">
                비밀번호 찾기
              </Link>
              <Link className="button secondary" to="/login">
                로그인
              </Link>
            </div>
          </>
        ) : (
          <>
            <div className="proto-result" role="status">
              <h3>일치하는 회원 정보를 찾지 못했습니다.</h3>
            </div>
            <div className="proto-actions">
              <button className="button" type="button" onClick={() => setResult(null)}>
                다시 찾기
              </button>
              <Link className="button secondary" to="/join">
                회원가입
              </Link>
            </div>
          </>
        )}
      </div>
    </ServicePage>
  );
}