// 시안에서 쓰는 선형 SVG 아이콘. 장식용이라 스크린리더에서는 숨긴다
import type { ReactElement } from 'react';

function Icon({ children }: { children: ReactElement | ReactElement[] }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
      {children}
    </svg>
  );
}

export const SearchIcon = () => (
  <Icon>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="m16 16 5 5" />
  </Icon>
);

export const CardIcon = () => (
  <Icon>
    <rect x="2" y="5" width="20" height="14" rx="2" />
    <path d="M2 10h20M6 15h4" />
  </Icon>
);

export const ListIcon = () => (
  <Icon>
    <rect x="5" y="3" width="14" height="18" rx="1.5" />
    <path d="M9 8h6M9 12h6M9 16h4" />
  </Icon>
);

export const PinIcon = () => (
  <Icon>
    <path d="M19 10c0 5-7 12-7 12S5 15 5 10a7 7 0 0 1 14 0Z" />
    <circle cx="12" cy="10" r="2.4" />
  </Icon>
);

export const ArrowIcon = () => (
  <Icon>
    <path d="M3 12h18m-6-6 6 6-6 6" />
  </Icon>
);
