// 청사 사진이 실제로 있는지 확인하는 훅. 사진은 git에 없어서 없으면 대체 화면(남색 배경)으로 둔다
import { useEffect, useState } from 'react';

export const BUILDING_PHOTO = '/dev-assets/building.jpg';

export type PhotoStatus = 'loading' | 'ok' | 'failed';

const probes = new Map<string, Promise<boolean>>();

function probe(src: string): Promise<boolean> {
  let result = probes.get(src);
  if (!result) {
    result = new Promise<boolean>((resolve) => {
      const image = new Image();
      image.onload = () => resolve(true);
      image.onerror = () => resolve(false);
      image.src = src;
    });
    probes.set(src, result);
  }
  return result;
}

export function usePhoto(src: string): PhotoStatus {
  const [status, setStatus] = useState<PhotoStatus>('loading');
  useEffect(() => {
    let active = true;
    void probe(src).then((ok) => {
      if (active) setStatus(ok ? 'ok' : 'failed');
    });
    return () => {
      active = false;
    };
  }, [src]);
  return status;
}

/** 시설 이름과 같은 이름의 사진 파일. 청사 사진처럼 git과 운영 빌드에 넣지 않는다 */
export const facilityPhoto = (name: string) => `/dev-assets/facility/${encodeURIComponent(name)}.jpg`;

/** 여러 사진 가운데 실제로 불러와진 것의 주소 */
export function useLoadedPhotos(sources: string[]): ReadonlySet<string> {
  const [loaded, setLoaded] = useState<ReadonlySet<string>>(new Set());
  const joined = sources.join('\n');
  useEffect(() => {
    let active = true;
    const list = joined ? joined.split('\n') : [];
    void Promise.all(list.map(async (src) => ((await probe(src)) ? src : ''))).then((found) => {
      if (active) setLoaded(new Set(found.filter(Boolean)));
    });
    return () => {
      active = false;
    };
  }, [joined]);
  return loaded;
}
