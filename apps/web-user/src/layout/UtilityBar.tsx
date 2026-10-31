// 화면 선택(기본·쉬운·관리자), 글자 크기 조절, SNS 아이콘이 있는 맨 위 띠
import facebook from '@jori/ui/assets/sns-facebook.png';
import kakao from '@jori/ui/assets/sns-kakao.png';
import youtube from '@jori/ui/assets/sns-youtube.png';
import type { ViewMode } from '@jori/ui';
import { Link, useLocation } from 'react-router-dom';
import { useViewMode } from '../view/ViewModeProvider';

function useViewHref() {
  const { pathname, search } = useLocation();
  return (view: ViewMode) => {
    const params = new URLSearchParams(search);
    params.set('view', view);
    return `${pathname}?${params.toString()}`;
  };
}

export function UtilityBar() {
  const { view, textSize, changeTextSize, canChangeTextSize } = useViewMode();
  const viewHref = useViewHref();

  return (
    <div className="utility-bar">
      <nav className="view-picker" aria-label="화면 선택">
        <Link to={viewHref('standard')} aria-current={view === 'standard' ? 'true' : 'false'}>
          기본 화면
        </Link>
        <Link to={viewHref('easy')} aria-current={view === 'easy' ? 'true' : 'false'}>
          쉬운 화면
        </Link>
        {/* 관리자 앱은 별도 빌드라 일반 링크로 이동한다. */}
        <a href="/admin/">관리자</a>
      </nav>
      <div className="text-tools" role="group" aria-label="글자 크기 조절">
        <span>글자 크기</span>
        <div className="text-size-buttons">
          <button
            type="button"
            aria-label="글자 작게"
            disabled={!canChangeTextSize(-10)}
            onClick={() => changeTextSize(-10)}
          >
            −
          </button>
          <button type="button" aria-label="글자 크기 기본으로" title="기본 크기로" onClick={() => changeTextSize(0)}>
            가
          </button>
          <button
            type="button"
            aria-label="글자 크게"
            disabled={!canChangeTextSize(10)}
            onClick={() => changeTextSize(10)}
          >
            +
          </button>
        </div>
        <span className="sr-only" role="status">
          글자 크기 {textSize}%
        </span>
      </div>
      <div className="social-tools" role="group" aria-label="SNS">
        <span title="페이스북">
          <img src={facebook} alt="페이스북" />
        </span>
        <span title="유튜브">
          <img src={youtube} alt="유튜브" />
        </span>
        <span title="카카오톡">
          <img src={kakao} alt="카카오톡" />
        </span>
      </div>
    </div>
  );
}
