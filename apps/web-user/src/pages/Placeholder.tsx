// 아직 시안을 옮기지 않은 화면의 임시 자리. 이식이 끝나면 해당 경로가 이 목록에서 빠진다
import { Link } from 'react-router-dom';
import { usePageTitle } from '../lib/usePageTitle';

export function Placeholder({ title }: { title: string }) {
  usePageTitle(title);
  return (
    <section className="wrap placeholder">
      <h1>{title}</h1>
      <p>이 화면은 아직 이식 전입니다.</p>
      <Link className="button secondary" to="/">
        홈으로
      </Link>
    </section>
  );
}

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
