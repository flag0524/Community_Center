// 쪽 번호. 현재 쪽은 강조된 숫자이고 나머지는 같은 조건의 다른 쪽으로 가는 링크다
import { Link } from 'react-router-dom';

export function Pager({ page, totalPages, hrefFor }: { page: number; totalPages: number; hrefFor: (page: number) => string }) {
  if (totalPages < 1) return null;
  const pages = Array.from({ length: totalPages }, (_, index) => index + 1);
  return (
    <nav className="pager" aria-label="쪽 이동">
      {pages.map((number) =>
        number === page ? (
          <strong key={number} aria-current="page">
            <span className="sr-only">현재 </span>
            {number}
            <span className="sr-only">쪽</span>
          </strong>
        ) : (
          // 보이는 숫자가 이름에 낱말로 들어가야 한다(WCAG 2.5.3). '2쪽'이 아니라 '2 쪽'이다.
          <Link key={number} to={hrefFor(number)} aria-label={`${number} 쪽`}>
            {number}
          </Link>
        ),
      )}
    </nav>
  );
}
