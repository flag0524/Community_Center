// 모든 주민 화면이 공유하는 틀. 본문 바로가기, 머리글, 전체 메뉴, 본문 자리, 바닥글을 묶는다
import { useRef } from 'react';
import { Outlet, useMatches } from 'react-router-dom';
import { AllMenu } from './AllMenu';
import { EasyHelp, Footer } from './Footer';
import { Header } from './Header';
import { UtilityBar } from './UtilityBar';

export function Layout() {
  const menuRef = useRef<HTMLDialogElement>(null);
  // 라우트가 handle.mainClass를 지정하면 본문 영역(main)에 그 클래스를 붙인다. 가장 안쪽 라우트가 우선한다.
  const mainClass = useMatches()
    .map((match) => (match.handle as { mainClass?: string } | undefined)?.mainClass)
    .reverse()
    .find(Boolean);

  return (
    <>
      <a className="skip" href="#main">
        본문 바로가기
      </a>
      <UtilityBar />
      <Header onOpenMenu={() => menuRef.current?.showModal()} />
      <AllMenu ref={menuRef} />
      <main id="main" className={mainClass}>
        <Outlet />
      </main>
      <EasyHelp />
      <Footer />
    </>
  );
}
