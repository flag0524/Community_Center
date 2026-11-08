// 홈의 팝업. 서버가 게시기간 안의 것만 내려주고 화면은 닫기와 `오늘 하루 보지 않기`만 맡는다. 포커스를 가져가지 않는 안내 창이다
import { useId, useState } from 'react';
import type { HomeResponse } from '../api/queries';
import { toKstDate } from '../lib/format';
import { ContentLink } from './ContentLink';

const hiddenKey = (contentId: string) => `popup-hidden:${contentId}`;

function hiddenToday(contentId: string, today: string): boolean {
  try {
    return window.localStorage.getItem(hiddenKey(contentId)) === today;
  } catch {
    return false; // 저장소를 쓸 수 없으면 계속 보인다
  }
}

function Popup({ popup, today, onClose }: { popup: HomeResponse['popups'][number]; today: string; onClose: () => void }) {
  const titleId = useId();
  const hideToday = () => {
    try {
      window.localStorage.setItem(hiddenKey(popup.contentId), today);
    } catch {
      // 저장하지 못해도 이번에는 닫는다.
    }
    onClose();
  };
  return (
    <section className="home-popup" role="dialog" aria-modal="false" aria-labelledby={titleId}>
      <h2 id={titleId}>{popup.title}</h2>
      {popup.image ? <img src={popup.image.url} alt={popup.image.alt} /> : null}
      {popup.body ? <p>{popup.body}</p> : null}
      {popup.linkUrl ? (
        <ContentLink url={popup.linkUrl} className="home-popup-link">
          자세히 보기
        </ContentLink>
      ) : null}
      <div className="home-popup-actions">
        <button className="button secondary" type="button" onClick={hideToday}>
          오늘 하루 보지 않기
        </button>
        <button className="button" type="button" onClick={onClose}>
          닫기
        </button>
      </div>
    </section>
  );
}

export function HomePopups({ popups, serverNow }: { popups: HomeResponse['popups']; serverNow: string }) {
  const [closed, setClosed] = useState<string[]>([]);
  const today = toKstDate(serverNow);
  const visible = popups.filter((popup) => !closed.includes(popup.contentId) && !hiddenToday(popup.contentId, today));
  if (visible.length === 0) return null;
  return (
    <div className="home-popups">
      {visible.map((popup) => (
        <Popup key={popup.contentId} popup={popup} today={today} onClose={() => setClosed((current) => [...current, popup.contentId])} />
      ))}
    </div>
  );
}