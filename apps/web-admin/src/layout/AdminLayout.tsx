// 관리자 공통 레이아웃. 상단 업무 묶음, 왼쪽 하위 메뉴, 전체 메뉴, 세션 표시를 권한 응답의 메뉴로 그린다 (ADM-CMN-001)
import logo from '@jori/ui/assets/paju-ci.jpg';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { ApiRequestError } from '../api/http';
import { permissionsQuery, sessionQuery } from '../api/queries';
import { errorMessage } from '../lib/errors';
import { findGroup } from './menu';
import { SessionClock } from './SessionClock';
import { useExpire } from './useExpire';
import { useLogout } from './useLogout';

export function AdminLayout() {
  const { pathname } = useLocation();
  const permissions = useQuery(permissionsQuery);
  const { data: session } = useQuery(sessionQuery);
  const logout = useLogout();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const allMenu = useRef<HTMLDialogElement>(null);

  const expire = useExpire();
  const unauthenticated = permissions.error instanceof ApiRequestError && permissions.error.status === 401;

  useEffect(() => setDrawerOpen(false), [pathname]);
  useEffect(() => {
    if (unauthenticated) expire();
    // expire는 렌더마다 새로 만들어지므로 의존성에 넣지 않는다. 만료는 한 번만 처리하면 된다.
  }, [unauthenticated]);

  if (unauthenticated) return null;
  if (permissions.isError) {
    return <p className="adm-loading" role="alert">{errorMessage(permissions.error)}</p>;
  }
  if (!permissions.data) return <p className="adm-loading" role="status">불러오는 중입니다.</p>;

  const { menu, roleNames } = permissions.data;
  const current = findGroup(menu, pathname);
  const sideGroup = current ?? menu[0];

  return (
    <>
      <a className="adm-skip" href="#admin-main">
        본문 바로가기
      </a>
      <header className="adm-topbar">
        <Link to="/" className="adm-brand" aria-label="조리읍주민자치센터 관리자 홈">
          <img src={logo} alt="파주시" />
          <div className="adm-brand-title">
            <strong>조리읍</strong>
            <span>주민자치센터</span>
          </div>
        </Link>
        <button
          className="adm-menu-toggle"
          type="button"
          aria-expanded={drawerOpen}
          aria-controls="admin-navigation"
          onClick={() => setDrawerOpen((open) => !open)}
        >
          메뉴
        </button>
        <nav className="adm-primary" aria-label="주요 업무">
          {menu.map((group) => (
            <Link key={group.key} to={group.items[0]!.path} aria-current={group === current ? 'page' : undefined}>
              {group.title}
            </Link>
          ))}
        </nav>
        <div className="adm-top-tools">
          <p className="adm-who">
            {session?.admin?.name} · {roleNames.join(', ')}
          </p>
          <SessionClock />
          <button type="button" onClick={() => allMenu.current?.showModal()}>
            전체 메뉴
          </button>
          <button type="button" onClick={() => logout.mutate()} disabled={logout.isPending}>
            로그아웃
          </button>
          {logout.isError && (
            <p className="adm-message error" role="alert">
              {errorMessage(logout.error)}
            </p>
          )}
        </div>
      </header>
      <aside className={drawerOpen ? 'adm-sidebar open' : 'adm-sidebar'} id="admin-navigation">
        {sideGroup && (
          <>
            <h2 className="adm-side-title">{sideGroup.title}</h2>
            <nav aria-label={`${sideGroup.title} 하위 메뉴`}>
              <section className="adm-nav-group">
                {sideGroup.items.map((item) => (
                  <NavLink key={item.key} to={item.path}>
                    {item.label}
                  </NavLink>
                ))}
              </section>
            </nav>
          </>
        )}
      </aside>
      <div className="adm-workspace">
        <main id="admin-main">
          <Outlet />
          <footer className="adm-footer">조리읍주민자치센터 관리 시스템</footer>
        </main>
      </div>
      <dialog
        ref={allMenu}
        id="admin-all-menu"
        className="adm-dialog adm-all-menu"
        aria-labelledby="admin-all-menu-title"
        // 어두운 바깥 영역(dialog 자신)을 누르면 닫는다.
        onClick={(event) => event.target === event.currentTarget && allMenu.current?.close()}
      >
        <div className="adm-dialog-head">
          <h2 id="admin-all-menu-title">전체 메뉴</h2>
          <button type="button" className="adm-icon-button" aria-label="전체 메뉴 닫기" onClick={() => allMenu.current?.close()}>
            ×
          </button>
        </div>
        <nav aria-label="전체 관리자 메뉴">
          {menu.map((group) => (
            <section className="adm-nav-group" key={group.key}>
              <h3>{group.title}</h3>
              {group.items.map((item) => (
                <Link key={item.key} to={item.path} onClick={() => allMenu.current?.close()}>
                  {item.label}
                </Link>
              ))}
            </section>
          ))}
        </nav>
      </dialog>
    </>
  );
}