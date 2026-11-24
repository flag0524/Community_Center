// 서브 페이지 틀 두 가지. 목록형은 히어로와 좌측 메뉴를, 상세형은 현재 위치와 제목을 쓴다
import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Breadcrumb, type Crumb } from '../components/Breadcrumb';
import { PhoneLink } from '../components/PhoneLink';
import { usePhoto, BUILDING_PHOTO } from '../lib/usePhoto';
import { NAV_GROUPS, type NavGroup } from './navigation';
import { useContact } from './useContact';

function SideMenu({ group, activeTo }: { group: NavGroup; activeTo?: string }) {
  const { pathname } = useLocation();
  const contact = useContact();
  return (
    <aside className={group.easyVisible ? 'side-menu easy-visible' : 'side-menu'}>
      <h2>{group.title}</h2>
      <nav aria-label={`${group.title} 하위 메뉴`}>
        <ul>
          {group.items.map((item) => (
            <li key={item.to}>
              <Link to={item.to} aria-current={(activeTo ?? pathname) === item.to ? 'page' : undefined}>
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
  activeTo,
  children,
}: {
  group: NavGroup;
  title: string;
  subtitle: string;
  crumbs: Crumb[];
  /** 좌측 메뉴에서 현재 항목으로 표시할 경로. 없으면 현재 주소와 같은 항목이다 */
  activeTo?: string;
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
          <SideMenu group={group} activeTo={activeTo} />
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

const MY_PAGE_GROUP = NAV_GROUPS.find((group) => group.title === '마이페이지')!;

/** 현재 주소가 속한 마이페이지 메뉴 항목. 상세·하위 화면은 가장 긴 접두부가 맞는 항목, 회원정보 하위(비밀번호·이름·탈퇴)는 회원정보수정이다 */
function myPageActive(pathname: string): string | undefined {
  if (/^\/me\/(password|name-change|withdraw)$/.test(pathname)) return '/me/profile';
  return MY_PAGE_GROUP.items
    .map((item) => item.to)
    .filter((to) => pathname === to || pathname.startsWith(`${to}/`))
    .sort((a, b) => b.length - a.length)[0];
}

/** 마이페이지 화면의 틀. 다른 메뉴와 같은 히어로와 좌측 메뉴를 쓰고, 현재 항목은 주소에서 정한다 */
export function MyPageLayout({ title, crumbs, children }: { title: string; crumbs: Crumb[]; children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <SubLayout
      group={MY_PAGE_GROUP}
      title={title}
      subtitle="내 신청과 회원정보를 확인합니다."
      crumbs={crumbs}
      activeTo={myPageActive(pathname)}
    >
      {children}
    </SubLayout>
  );
}

export const SERVICE_PAGE_HANDLE = { mainClass: 'service-page' } as const;
