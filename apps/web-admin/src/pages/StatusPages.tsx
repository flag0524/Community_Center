// 권한이 없는 화면과 없는 주소의 안내 화면
import { Link } from 'react-router-dom';

export function ForbiddenPage() {
  return (
    <>
      <div className="adm-page-heading">
        <h1>이용 권한이 없습니다</h1>
      </div>
      <p>이 화면을 볼 수 있는 권한이 배정되어 있지 않습니다. 필요하면 권한 배정 담당자에게 문의해 주세요.</p>
      <p>
        <Link to="/">처음 화면으로</Link>
      </p>
    </>
  );
}

export function NotFoundPage() {
  return (
    <>
      <div className="adm-page-heading">
        <h1>페이지를 찾을 수 없습니다</h1>
      </div>
      <p>주소가 바뀌었거나 없는 화면입니다.</p>
      <p>
        <Link to="/">처음 화면으로</Link>
      </p>
    </>
  );
}