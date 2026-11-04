// 없는 주소를 열었을 때 보이는 찾을 수 없음 화면
import { Link } from 'react-router-dom';
import { usePageTitle } from '../lib/usePageTitle';

export function NotFound() {
  usePageTitle('페이지를 찾을 수 없습니다');
  return (
    <section className="wrap placeholder">
      <h1>페이지를 찾을 수 없습니다</h1>
      <p>주소를 다시 확인하시거나 홈에서 다시 찾아 주세요.</p>
      <Link className="button secondary" to="/">
        홈으로
      </Link>
    </section>
  );
}
