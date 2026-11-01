// 회원가입 1단계. 필수 약관 두 가지에 동의해야 본인확인으로 넘어간다
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { FormMessage } from '../../components/FormMessage';
import { ServicePage } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';
import { useJoinFlow } from './JoinFlow';

const TITLE = '회원가입 · 약관동의';

export function JoinTermsPage() {
  usePageTitle(TITLE);
  const navigate = useNavigate();
  const { draft, update } = useJoinFlow();
  const [terms, setTerms] = useState(draft.agreed);
  const [privacy, setPrivacy] = useState(draft.agreed);
  const [message, setMessage] = useState('');

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!terms || !privacy) {
      setMessage('필수 약관에 모두 동의해 주세요.');
      return;
    }
    update({ agreed: true });
    navigate('/join/verify');
  }

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '회원서비스' }, { label: TITLE }]}>
      <div className="proto">
        <h2>약관동의</h2>
        <form className="proto-form" aria-label="약관동의" noValidate onSubmit={submit}>
          <div className="proto-consent">
            <h3>이용약관</h3>
            <p>서비스 이용조건과 신청·결제 안내를 확인해 주세요.</p>
            {/* 같은 창에서 열면 가입 진행 정보를 잃으므로 새 창으로 연다. 이름은 보이는 글자를 낱말 단위로 포함한다(WCAG 2.5.3). */}
            <a href="/terms/terms-of-use" target="_blank" rel="noopener" aria-label="이용약관 보기 (새 창)">
              이용약관 보기
            </a>
            <label>
              <input type="checkbox" checked={terms} onChange={(event) => setTerms(event.target.checked)} /> 이용약관에
              동의합니다. (필수)
            </label>
          </div>
          <div className="proto-consent">
            <h3>개인정보 수집·이용 안내</h3>
            <p>개인정보 처리 목적과 항목, 보유기간 및 권리 안내를 확인해 주세요.</p>
            <a href="/terms/privacy-policy" target="_blank" rel="noopener" aria-label="개인정보 안내 보기 (새 창)">
              개인정보 안내 보기
            </a>
            <label>
              <input type="checkbox" checked={privacy} onChange={(event) => setPrivacy(event.target.checked)} />{' '}
              개인정보 수집·이용 안내에 동의합니다. (필수)
            </label>
          </div>
          <div className="proto-form-actions">
            <button className="button" type="submit">
              다음
            </button>
          </div>
          <FormMessage text={message} error />
        </form>
      </div>
    </ServicePage>
  );
}
