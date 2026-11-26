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
