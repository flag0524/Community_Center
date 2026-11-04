// 아직 만들지 않은 관리자 화면의 임시 자리. 단계마다 실제 화면으로 바꾸고 마지막에 지운다
import { useLocation } from 'react-router-dom';
import { useMenuLabel } from '../layout/menu';

export function ComingSoonPage() {
  const label = useMenuLabel(useLocation().pathname);
  return (
    <>
      <div className="adm-page-heading">
        <h1>{label}</h1>
      </div>
      <p className="adm-muted">이 화면은 다음 단계에서 제공됩니다.</p>
    </>
  );
}