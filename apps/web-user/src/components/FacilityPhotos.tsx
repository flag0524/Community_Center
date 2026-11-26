// 시설 사진. 대표 사진과 장수를 단추로 보이고, 누르면 큰 창에서 이전·다음으로 넘겨 본다
import { useEffect, useId, useRef, useState } from 'react';

export interface PhotoSet {
  name: string;
  urls: string[];
}

export function PhotoButton({ name, urls, onOpen }: PhotoSet & { onOpen: (photos: PhotoSet) => void }) {
  const label = `사진 ${urls.length}장 크게 보기`;
  return (
    <button type="button" className="facility-photo-button" aria-label={`${name} ${label}`} onClick={() => onOpen({ name, urls })}>
      <img className="facility-photo" src={urls[0]} alt="" />
      <span>{label}</span>
    </button>
  );
}

/** 초점 가둠, Esc 닫기, 누른 단추로의 초점 복귀는 dialog 요소가 맡는다. */
export function PhotoViewer({ photos, onClose }: { photos: PhotoSet; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [index, setIndex] = useState(0);
  const total = photos.urls.length;
  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal();
  }, []);

  return (
    <dialog ref={dialog} className="photo-viewer" aria-labelledby={titleId} onClose={onClose}>
      <h2 id={titleId}>{photos.name} 사진</h2>
      <img src={photos.urls[index]} alt={`${photos.name} 사진 ${index + 1} / ${total}`} />
      <div className="photo-viewer-actions">
        {total > 1 ? (
          <>
            <button type="button" className="button secondary" disabled={index === 0} onClick={() => setIndex(index - 1)}>
              이전 사진
            </button>
            <span role="status">
              {index + 1} / {total}
            </span>
            <button type="button" className="button secondary" disabled={index === total - 1} onClick={() => setIndex(index + 1)}>
              다음 사진
            </button>
          </>
        ) : null}
        <button type="button" className="button" onClick={() => dialog.current?.close()}>
          닫기
        </button>
      </div>
    </dialog>
  );
}
