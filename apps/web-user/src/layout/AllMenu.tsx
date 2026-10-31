// 전체 메뉴를 보여 주는 모달 대화상자. 초점 가둠, Esc 닫기, 호출자 초점 복귀는 dialog 요소가 맡는다
import { forwardRef } from 'react';
import { Link } from 'react-router-dom';
import { NAV_GROUPS } from './navigation';

export const AllMenu = forwardRef<HTMLDialogElement>(function AllMenu(_props, ref) {
  function close(dialog: HTMLDialogElement | null) {
    dialog?.close();
  }

  return (
    <dialog
      id="all-menu"
      ref={ref}
      aria-labelledby="menu-title"
      onClick={(event) => {
        // 바깥(어두운 영역)을 누르면 닫는다.
        if (event.target === event.currentTarget) close(event.currentTarget);
      }}
    >
      <div className="menu-dialog-head">
        <h2 id="menu-title">전체 메뉴</h2>
        <button
          className="close-menu"
          type="button"
          aria-label="전체 메뉴 닫기"
          onClick={(event) => close(event.currentTarget.closest('dialog'))}
        >
          ×
        </button>
      </div>
      <nav className="menu-tree" aria-label="전체 메뉴 트리">
        {NAV_GROUPS.map((group) => (
          <section key={group.to}>
            <h3>{group.title}</h3>
            {group.items.map((item) => (
              <Link key={item.to} to={item.to} onClick={(event) => close(event.currentTarget.closest('dialog'))}>
                {item.label}
              </Link>
            ))}
          </section>
        ))}
      </nav>
      <div className="menu-dialog-foot">조리읍주민자치센터　·　함께 배우고, 함께 자라는 조리읍.</div>
    </dialog>
  );
});
