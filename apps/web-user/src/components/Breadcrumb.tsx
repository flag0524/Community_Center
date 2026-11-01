// 현재 위치를 보여 주는 경로 표시. 마지막 항목은 현재 화면이라 링크가 아니다
import { Fragment } from 'react';
import { Link } from 'react-router-dom';

export interface Crumb {
  label: string;
  to?: string;
}

export function Breadcrumb({ items }: { items: Crumb[] }) {
  const trail: Crumb[] = [{ label: '홈', to: '/' }, ...items];
  return (
    <nav className="breadcrumb" aria-label="현재 위치">
      {trail.map((item, index) => {
        const last = index === trail.length - 1;
        // 시안은 구분 기호와 글자가 같은 줄의 형제 요소라서 묶지 않고 나란히 둔다.
        return (
          <Fragment key={`${index}-${item.label}`}>
            {index > 0 ? (
              <span className="separator" aria-hidden="true">
                ›
              </span>
            ) : null}
            {last ? <strong>{item.label}</strong> : item.to ? <Link to={item.to}>{item.label}</Link> : <span>{item.label}</span>}
          </Fragment>
        );
      })}
    </nav>
  );
}
