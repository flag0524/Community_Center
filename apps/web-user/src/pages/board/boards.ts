// 읽기 게시판의 화면 이름과 주소. 키는 서버의 게시판 키와 같다
import type { BoardKey } from '../../api/queries';

export type ReadBoardKey = Extract<BoardKey, 'notice' | 'news' | 'resources' | 'gallery' | 'faq'>;

export const BOARDS: Record<ReadBoardKey, { title: string; path: string }> = {
  notice: { title: '공지사항', path: '/board/notice' },
  news: { title: '기관소식', path: '/board/news' },
  resources: { title: '자료실', path: '/board/resources' },
  gallery: { title: '센터 갤러리', path: '/board/gallery' },
  faq: { title: '자주하는 질문', path: '/board/faq' },
};

export const COMMUNITY_GROUP_TITLE = '커뮤니티';
export const fileUrl = (fileId: string) => `/api/v1/files/${fileId}`;
export const paragraphs = (text: string) => text.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean);