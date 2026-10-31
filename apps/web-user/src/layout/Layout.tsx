// 모든 주민 화면이 공유하는 틀. 본문 바로가기, 머리글, 전체 메뉴, 본문 자리, 바닥글을 묶는다
import { useRef } from 'react';
import { Outlet } from 'react-router-dom';
import { AllMenu } from './AllMenu';
import { EasyHelp, Footer } from './Footer';
import { Header } from './Header';
import { UtilityBar } from './UtilityBar';

export function Layout() {
  const menuRef = useRef<HTMLDialogElement>(null);

  return (
    <>
      <a className="skip" href="#main">
        본문 바로가기
      </a>
      <UtilityBar />
      <Header onOpenMenu={() => menuRef.current?.showModal()} />
      <AllMenu ref={menuRef} />
      <main id="main">
        <Outlet />
      </main>
      <EasyHelp />
      <Footer />
    </>
  );
}
