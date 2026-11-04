// 주 메뉴, 전체 메뉴, 푸터 링크가 함께 쓰는 메뉴 정의. 경로는 TDD 9.2를 따른다
export interface NavLinkItem {
  label: string;
  to: string;
}

export interface NavGroup {
  title: string;
  to: string;
  items: NavLinkItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    title: '강좌정보',
    to: '/courses',
    items: [
      { label: '전체 강좌', to: '/courses' },
      { label: '접수중 강좌', to: '/courses/open' },
      { label: '접수예정 강좌', to: '/courses/upcoming' },
      { label: '수강 및 결제 안내', to: '/guide/apply' },
      { label: '환불 및 휴강일 안내', to: '/guide/refund' },
    ],
  },
  {
    title: '강사은행',
    to: '/instructors',
    items: [
      { label: '강사현황', to: '/instructors' },
      { label: '강사등록신청', to: '/instructors/recruit' },
    ],
  },
  {
    title: '커뮤니티',
    to: '/board/notice',
    items: [
      { label: '공지사항', to: '/board/notice' },
      { label: '자료실', to: '/board/resources' },
      { label: '기관소식', to: '/board/news' },
      { label: '수강후기', to: '/board/review' },
      { label: '질문과 답변', to: '/board/qna' },
      { label: '자주하는 질문', to: '/board/faq' },
      { label: '센터 갤러리', to: '/board/gallery' },
    ],
  },
  {
    title: '센터소개',
    to: '/center/history',
    items: [
      { label: '연혁', to: '/center/history' },
      { label: '시설안내', to: '/center/facility' },
      { label: '위치 및 연락처', to: '/center/contact' },
    ],
  },
  {
    title: '마이페이지',
    to: '/me/applications',
    items: [
      { label: '수강신청내역', to: '/me/applications' },
      { label: '회원정보수정', to: '/me/profile' },
    ],
  },
];

export const EASY_NAV: NavLinkItem[] = [
  { label: '강좌 찾기', to: '/courses' },
  { label: '내 신청 확인', to: '/me/applications' },
  { label: '센터 문의', to: '/center/contact' },
];

export const FOOTER_LINKS: NavLinkItem[] = [
  { label: '개인정보처리방침', to: '/terms/privacy-policy' },
  { label: '이용약관', to: '/terms/terms-of-use' },
  { label: '이메일무단수집거부', to: '/terms/email-refusal' },
];

export function isActiveGroup(group: NavGroup, pathname: string): boolean {
  const roots = new Set([group.to, ...group.items.map((item) => item.to)]);
  return [...roots].some((root) => pathname === root || pathname.startsWith(`${root}/`));
}
