// 목록 화면이 함께 쓰는 조각. 총 건수, 가로로 넘치는 표 영역, 쪽 번호 (ADM-CMN-002)
import { useEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

export function ResultCount({ total }: { total: number }) {
  return (
    <p className="adm-count" role="status">
      총 <strong>{total.toLocaleString('ko-KR')}</strong>건
    </p>
  );
}

/**
 * 표를 감싸는 영역. 좁은 화면(CSS)에서는 표의 한 행이 카드 하나로 쌓이고, 칸 앞에 열 이름이 붙는다.
 * 열 이름은 머리글 글자를 칸의 data-label로 옮겨 CSS가 쓴다. 행이 바뀔 때마다 다시 채운다.
 */
export function TableWrap({ label, children }: { label: string; children: ReactNode }) {
  const wrap = useRef<HTMLDivElement>(null);
  useEffect(() => {
    wrap.current?.querySelectorAll('table').forEach((table) => {
      const names = [...table.querySelectorAll('thead th')].map((head) => head.textContent?.trim() ?? '');
      table.querySelectorAll('tbody tr').forEach((row) => {
        [...row.children].forEach((cell, index) => cell.setAttribute('data-label', names[index] ?? ''));
      });
    });
  });
  useEffect(() => {
    // 좁은 화면·터치 기기에서는 라벨이 없는 칸 안의 체크박스·라디오를 칸 어디를 눌러도 켜지고 꺼지게 한다(누르는 칸 44px 이상).
    const element = wrap.current;
    if (!element) return undefined;
    const toggleFromCell = (event: MouseEvent) => {
      if (!window.matchMedia?.('(max-width: 760px), (pointer: coarse)').matches) return;
      const target = event.target as HTMLElement;
      if (target.closest('input, label, button, a, select, textarea')) return;
      const boxes = target.closest('td')?.querySelectorAll<HTMLInputElement>('input[type=checkbox], input[type=radio]');
      if (boxes?.length === 1) boxes[0]?.click();
    };
    element.addEventListener('click', toggleFromCell);
    return () => element.removeEventListener('click', toggleFromCell);
  }, []);
  return (
    <div className="adm-table-wrap" role="region" aria-label={label} tabIndex={0} ref={wrap}>
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
