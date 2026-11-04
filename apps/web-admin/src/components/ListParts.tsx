// 목록 화면이 함께 쓰는 조각. 총 건수, 가로로 넘치는 표 영역, 쪽 번호 (ADM-CMN-002)
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export function ResultCount({ total }: { total: number }) {
  return (
    <p className="adm-count" role="status">
      총 <strong>{total.toLocaleString('ko-KR')}</strong>건
    </p>
  );
}

/** 좁은 화면에서 표가 쪽 전체를 넘치게 하지 않고 이 영역 안에서만 가로로 움직이게 한다. */
export function TableWrap({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="adm-table-wrap" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}

interface PagerProps {
  page: number;
  total: number;
  size: number;
  hrefFor: (page: number) => string;
}

export function AdminPager({ page, total, size, hrefFor }: PagerProps) {
  const totalPages = Math.ceil(total / size);
  if (totalPages <= 1) return null;
  return (
    <nav className="adm-pager" aria-label="쪽 이동">
      {Array.from({ length: totalPages }, (_, index) => index + 1).map((number) =>
        number === page ? (
          <strong key={number} aria-current="page">
            {number}
          </strong>
        ) : (
          <Link key={number} to={hrefFor(number)} aria-label={`${number} 쪽`}>
            {number}
          </Link>
        ),
      )}
    </nav>
  );
}
