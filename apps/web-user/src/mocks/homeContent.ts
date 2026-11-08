// 모의 서버가 홈에 내려줄 비주얼·배너·팝업. 기본은 비어 있고 개발 서버에서만 주소의 mockHome=full로 시연한다
import type { Schemas } from '@jori/api-client';

type Home = Schemas['HomeResponse'];
export type HomeContent = Pick<Home, 'visual' | 'banners' | 'popups'>;
type Mode = 'full' | 'empty';

const STORAGE_KEY = 'mockHome';
let override: Mode | null = null;

const isMode = (value: string | null): value is Mode => value === 'full' || value === 'empty';

/** 시험에서 홈 콘텐츠를 고정한다. null이면 해제한다. */
export function setMockHomeContent(value: Mode | null): void {
  override = value;
}

function readMode(): Mode {
  if (override) return override;
  try {
    const stored = window.sessionStorage.getItem(STORAGE_KEY);
    return isMode(stored) ? stored : 'empty';
  } catch {
    return 'empty';
  }
}

/** 주소의 ?mockHome=full 을 읽어 세션에 기억한다. 빈 값이면 해제한다. 개발 서버에서만 호출된다. */
export function initMockHomeFromLocation(): void {
  try {
    const param = new URLSearchParams(window.location.search).get('mockHome');
    if (param === null) return;
    if (param === '') window.sessionStorage.removeItem(STORAGE_KEY);
    else if (isMode(param)) window.sessionStorage.setItem(STORAGE_KEY, param);
  } catch {
    // 저장소를 쓸 수 없으면 비워 둔다.
  }
}

/** 시연용 콘텐츠 이미지 번호. 파일 모의 서버가 이 번호를 이미지로 내려준다. */
export const CONTENT_IMAGE_IDS = ['9100000000000000000501', '9100000000000000000502', '9100000000000000000503'];
const image = (index: number, alt: string) => ({ url: `/api/v1/files/${CONTENT_IMAGE_IDS[index]}`, alt });

// 서버가 게시 여부와 게시기간을 판정해 지금 보일 것만 내려준다. 팝업은 연말까지만 보인다.
export function homeContent(now: Date): HomeContent {
  if (readMode() !== 'full') return { visual: null, banners: [], popups: [] };
  const popupOpen = now.getTime() < new Date('2027-01-01T00:00:00+09:00').getTime();
  return {
    visual: { title: '함께 배우고, 함께 자라는 조리읍.', body: '시험용 문구: 함께 배우는 즐거움', linkUrl: '/courses', image: image(0, '조리읍 행정복지센터 청사') },
    banners: [
      { contentId: '2000000000000000000003', title: '수강신청 접수 안내', linkUrl: '/guide/apply', image: image(1, '수강신청 접수 안내 배너') },
      { contentId: '2000000000000000000004', title: '접수 예정 안내', linkUrl: 'https://www.paju.go.kr', image: null },
    ],
    popups: popupOpen ? [{ contentId: '2000000000000000000005', title: '휴관일 안내', body: '11월 1일부터 10일까지 휴관합니다.', linkUrl: '/center/contact', image: image(2, '휴관일 안내 이미지') }] : [],
  };
}