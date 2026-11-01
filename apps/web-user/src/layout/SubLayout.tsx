// 서브 페이지 틀 두 가지. 목록형은 히어로와 좌측 메뉴를, 상세형은 현재 위치와 제목을 쓴다
import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Breadcrumb, type Crumb } from '../components/Breadcrumb';
import { PhoneLink } from '../components/PhoneLink';
import { usePhoto, BUILDING_PHOTO } from '../lib/usePhoto';
import type { NavGroup } from './navigation';
import { useContact } from './useContact';

function SideMenu({ group }: { group: NavGroup }) {
  const { pathname } = useLocation();
  const contact = useContact();
  return (
    <aside className="side-menu">
      <h2>{group.title}</h2>
      <nav aria-label={`${group.title} 하위 메뉴`}>
        <ul>
          {group.items.map((item) => (
            <li key={item.to}>
              <Link to={item.to} aria-current={pathname === item.to ? 'page' : undefined}>
                {item.label}
                <span aria-hidden="true">›</span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="side-contact">
        수강·센터 이용 문의
        <strong>
          <PhoneLink number={contact?.phone} />
        </strong>
        {contact?.floorInfo}
      </div>
    </aside>
  );
}

/** 히어로, 현재 위치, 좌측 메뉴, 본문으로 이루어진 목록형 서브 페이지 */
export function SubLayout({
  group,
  title,
  subtitle,
  crumbs,
  children,
}: {
  group: NavGroup;
  title: string;
  subtitle: string;
  crumbs: Crumb[];
  children: ReactNode;
}) {
  const photo = usePhoto(BUILDING_PHOTO);
  return (
    <>
      <section className="sub-hero">
        {photo === 'ok' ? <img src={BUILDING_PHOTO} alt="" /> : null}
        <div className="wrap">
          <div className="eyebrow">{group.title}</div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
      </section>
      <div className="wrap">
        <Breadcrumb items={crumbs} />
        <div className="sub-layout">
          <SideMenu group={group} />
          <div className="page-body">{children}</div>
        </div>
      </div>
    </>
  );
}

/** 현재 위치와 제목 아래에 본문이 오는 상세형 서브 페이지. main에 service-page 클래스가 필요하다 */
export function ServicePage({ title, crumbs, children }: { title: string; crumbs: Crumb[]; children: ReactNode }) {
  return (
    <div className="wrap">
      <Breadcrumb items={crumbs} />
      <div className="service-content">
        <header className="service-page-heading">
          <h1>{title}</h1>
        </header>
        <div className="page-body">{children}</div>
      </div>
    </div>
  );
}

export const SERVICE_PAGE_HANDLE = { mainClass: 'service-page' } as const;
