// 회원가입 완료 안내. 들어오면 가입 진행 정보를 지워 같은 본인확인으로 다시 가입하지 못하게 한다
import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ServicePage } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';
import { useJoinFlow } from './JoinFlow';

const TITLE = '회원가입 완료';

export function JoinCompletePage() {
  usePageTitle(TITLE);
  const { reset } = useJoinFlow();
  useEffect(() => {
    reset();
  }, [reset]);

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '회원서비스' }, { label: TITLE }]}>
      <div className="proto">
        <div className="proto-result">
          <h2>회원가입이 완료되었습니다.</h2>
          <p>로그인 후 강좌를 신청하실 수 있습니다.</p>
        </div>
        <div className="proto-actions">
          <Link className="button" to="/login">
            로그인
          </Link>
          <Link className="button secondary" to="/courses">
            강좌 목록
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}
