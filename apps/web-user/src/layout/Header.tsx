// 로고, 주 메뉴, 전체 메뉴 버튼, 강좌 검색, 로그인 링크가 있는 머리글
import logo from '@jori/ui/assets/paju-ci.jpg';
import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { SearchIcon } from '../components/icons';
import { EASY_NAV, NAV_GROUPS, isActiveGroup } from './navigation';
import { useContact } from './useContact';

export function Header({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const contact = useContact();
  const [query, setQuery] = useState('');

  function search(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    navigate(q ? `/courses?q=${encodeURIComponent(q)}` : '/courses');
  }

  return (
    <header className="header">
      <Link className="logo" to="/" aria-label="조리읍주민자치센터 홈">
        <img src={logo} alt="파주시" />
        <strong>
          조리읍<span>주민자치센터</span>
        </strong>
      </Link>
      <div className="navigation-group">
        <button
          className="menu-trigger"
          type="button"
          aria-label="전체 메뉴 열기"
          aria-haspopup="dialog"
          aria-controls="all-menu"
          onClick={onOpenMenu}
        >
          <span className="menu-lines" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span className="menu-label">전체 메뉴</span>
        </button>
        <nav className="easy-only easy-nav" aria-label="자주 쓰는 메뉴">
          {EASY_NAV.map((item) => (
            <Link key={item.to} to={item.to}>
              {item.label}
            </Link>
          ))}
        </nav>
        <nav className="primary-nav" aria-label="주 메뉴">
          {NAV_GROUPS.map((group) => (
            <div key={group.to} className={isActiveGroup(group, pathname) ? 'nav-item active' : 'nav-item'}>
              <Link to={group.to}>{group.title}</Link>
              <div className="dropdown">
                {group.items.map((item) => (
                  <Link key={item.to} to={item.to}>
                    {item.label}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </div>
      <div className="header-right">
        {contact?.phone ? (
          <a className="mobile-phone" href={`tel:${contact.phone}`} aria-label={`센터 전화 문의 ${contact.phone}`}>
            전화 문의
          </a>
        ) : null}
        <form className="header-search" onSubmit={search} role="search" aria-label="통합 검색">
          <input
            name="q"
            type="search"
            aria-label="통합 강좌 검색"
            placeholder="강좌를 검색해 보세요"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit" aria-label="강좌 검색">
            <SearchIcon />
          </button>
        </form>
        <Link className="login-link" to="/login">
          로그인
        </Link>
      </div>
    </header>
  );
}
