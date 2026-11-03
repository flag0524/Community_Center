// 회원탈퇴 완료 안내. 탈퇴하면 로그인 상태가 사라지므로 로그인이 필요 없는 화면으로 따로 둔다
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { sessionQuery } from '../../api/queries';
import { ServicePage } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '회원탈퇴 완료';

export function WithdrawDonePage() {
  usePageTitle(TITLE);
  const queryClient = useQueryClient();
  // 탈퇴로 세션이 사라졌다. 로그인이 필요 없는 이 화면이 뜬 뒤에 세션을 다시 받아 머리글을 비로그인으로 바꾼다.
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: sessionQuery.queryKey });
  }, [queryClient]);
  return (
    <ServicePage title={TITLE} crumbs={[{ label: '회원서비스' }, { label: TITLE }]}>
      <div className="proto">
        <div className="proto-result" role="status">
          <h2>회원탈퇴 처리가 완료되었습니다.</h2>
          <p>그동안 이용해 주셔서 감사합니다. 개인정보는 30일 뒤 파기됩니다.</p>
        </div>
        <div className="proto-actions">
          <Link className="button" to="/">
            처음 화면
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}