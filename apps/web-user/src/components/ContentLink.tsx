// 홈 콘텐츠의 링크. 사이트 안 경로는 앱 안에서 이동하고 https 주소는 새 창으로 열며 그 밖의 값은 링크로 만들지 않는다
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export function ContentLink({ url, className, children }: { url: string | null; className?: string; children: ReactNode }) {
  if (url?.startsWith('/') && !url.startsWith('//')) {
    return (
      <Link className={className} to={url}>
        {children}
      </Link>
    );
  }
  if (url?.startsWith('https://')) {
    return (
      <a className={className} href={url} target="_blank" rel="noopener noreferrer">
        {children}
        <span className="visually-hidden"> (새 창)</span>
      </a>
    );
  }
  return <span className={className}>{children}</span>;
}