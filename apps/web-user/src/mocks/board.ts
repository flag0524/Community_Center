
import { CONTENT_IMAGE_IDS } from './homeContent';// 모의 서버의 게시판 데이터와 첨부. 홈의 공지(101, 102)와 같은 게시물을 쓴다. 문안은 시안의 공식 자료다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';

type BoardKey = Schemas['BoardKey'];
type PostSummary = Schemas['PostSummary'];
type PostDetail = Schemas['PostDetail'];
type PostFile = Schemas['PostFile'];
type PostImage = Schemas['PostImage'];

const file = (fileId: string, name: string, contentType = 'application/pdf'): PostFile => ({
  fileId,
  name,
  sizeBytes: 1024,
  contentType,
});
const image = (fileId: string, alt: string): PostImage => ({ fileId, alt });

type StoredPost = PostDetail;

const NOTICE_FILES = [file('9001', '수강생 모집 안내 PDF'), file('9002', '교육프로그램 시간표 PDF')];
const BUILDING = image('9101', '조리읍 행정복지센터 신청사');

const POSTS: StoredPost[] = [
  {
    postId: '101',
    board: 'notice',
    title: '2026년 4분기 조리읍주민자치센터 수강생 모집',
    publishedAt: '2026-09-01T09:00:00+09:00',
    pinned: true,
    body: '방문 접수 후 계좌이체로 납부합니다. 현금·카드 납부는 불가합니다. 안내된 접수기간은 마감되었습니다.',
    facts: [
      { label: '교육기간', value: '2026.10.01 – 12.31' },
      { label: '접수기간', value: '2026.09.07 – 09.11' },
      { label: '접수시간', value: '09:00 – 18:00' },
      { label: '접수장소', value: '조리읍 행정복지센터 3층 주민자치회 사무실' },
      { label: '수강 문의', value: '031-941-7742', url: 'tel:031-941-7742' },
    ],
    attachments: NOTICE_FILES,
    images: [],
  },
  {
    postId: '102',
    board: 'notice',
    title: '2026년 통기타 강사 모집 공고',
    publishedAt: '2026-02-19T09:00:00+09:00',
    pinned: true,
    body: '통기타 강좌 강사를 모집합니다. 자세한 내용은 센터에 문의해 주세요.',
    facts: [],
    attachments: [],
    images: [],
  },
  {
    postId: '201',
    board: 'news',
    title: '조리읍 행정복지센터 신청사 개청',
    publishedAt: '2022-10-05T09:00:00+09:00',
    pinned: false,
    body: '조리읍 행정복지센터 신청사가 2022년 10월 5일 개청했습니다.',
    facts: [],
    attachments: [],
    images: [],
  },
  {
    postId: '301',
    board: 'resources',
    title: '2026년 4분기 교육프로그램 수강생 모집 안내',
    publishedAt: '2026-09-01T09:00:00+09:00',
    pinned: false,
    body: '조리읍 2026년 4분기 교육프로그램 공식 자료입니다.',
    facts: [],
    attachments: [file('9001', '2026년 4분기 교육프로그램 수강생 모집 안내 PDF')],
    images: [],
  },
  {
    postId: '302',
    board: 'resources',
    title: '2026년 4분기 교육프로그램 시간표',
    publishedAt: '2026-09-01T09:00:00+09:00',
    pinned: false,
    body: '조리읍 2026년 4분기 교육프로그램 시간표 공식 자료입니다.',
    facts: [],
    attachments: [file('9002', '2026년 4분기 교육프로그램 시간표 PDF')],
    images: [],
  },
  {
    postId: '401',
    board: 'gallery',
    title: '조리읍 행정복지센터 신청사',
    publishedAt: '2022-10-05T09:00:00+09:00',
    pinned: false,
    body: '파주시 공식 사진 자료입니다.',
    facts: [],
    attachments: [],
    images: [BUILDING],
  },
  {
    postId: '501',
    board: 'faq',
    title: '2026년 4분기 접수 방법',
    publishedAt: '2026-09-01T09:00:00+09:00',
    pinned: false,
    body: '9월 7일부터 11일까지 09:00–18:00에 조리읍 행정복지센터 3층 주민자치센터 사무실에서 방문 접수합니다. 접수기간은 마감되었습니다.',
    facts: [],
    attachments: [],
    images: [],
  },
  {
    postId: '502',
    board: 'faq',
    title: '현행 수강료 납부 방법',
    publishedAt: '2026-09-01T09:00:00+09:00',
    pinned: false,
    body: '모집 안내의 납부 방식은 계좌이체입니다. 현금·카드 납부는 불가합니다.',
    facts: [],
    attachments: [],
    images: [],
  },
  {
    postId: '503',
    board: 'faq',
    title: '온라인 신청과 10분 결제기한',
    publishedAt: '2026-09-01T09:00:00+09:00',
    pinned: false,
    body: '유료 자리를 배정받으면 10분(600초) 안에 결제해야 하며 새로고침·재접속·결제수단 변경으로 연장되지 않습니다. 승인 결과 불명 거래는 확인 전 재결제와 자리 반환을 보류합니다.',
    facts: [],
    attachments: [],
    images: [],
  },
];

const READABLE: BoardKey[] = ['notice', 'news', 'resources', 'gallery', 'faq'];

function summarize(post: StoredPost): PostSummary {
  return {
    postId: post.postId,
    board: post.board,
    title: post.title,
    publishedAt: post.publishedAt,
    pinned: post.pinned,
    body: post.board === 'faq' ? post.body : null,
    primaryFile: post.attachments[0] ?? null,
    thumbnail: post.images[0] ?? null,
  };
}

const notFound = () =>
  HttpResponse.json({ code: 'NOT_FOUND', message: '요청한 정보를 찾을 수 없습니다.', requestId: 'mock-not-found-0001' }, { status: 404 });

// 첨부 내용은 시험용 자리표시다. 이미지는 SVG, 그 밖은 짧은 문서 문구를 돌려준다.
const PLACEHOLDER_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="100%" height="100%" fill="#44546a"/><text x="50%" y="50%" fill="#fff" font-size="24" text-anchor="middle">시험용 이미지</text></svg>';

export const boardHandlers = [
  http.get('/api/v1/boards/:board/posts', ({ params, request }) => {
    const board = String(params.board) as BoardKey;
    if (!READABLE.includes(board)) return notFound();
    const search = new URL(request.url).searchParams;
    const q = search.get('q')?.trim().toLowerCase();
    const page = Math.max(1, Number(search.get('page')) || 1);
    const size = Math.min(50, Math.max(1, Number(search.get('size')) || 10));
    const matched = POSTS.filter((post) => post.board === board && (!q || post.title.toLowerCase().includes(q)))
      .sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.publishedAt.localeCompare(a.publishedAt));
    return HttpResponse.json({
      items: matched.slice((page - 1) * size, page * size).map(summarize),
      page,
      size,
      total: matched.length,
      criteria: { basisAt: new Date().toISOString(), description: null },
    });
  }),

  http.get('/api/v1/posts/:postId', ({ params }) => {
    const post = POSTS.find((item) => item.postId === String(params.postId));
    return post ? HttpResponse.json(post) : notFound();
  }),

  http.get('/api/v1/files/:fileId', ({ params }) => {
    const id = String(params.fileId);
    const all = [...POSTS.flatMap((post) => [...post.attachments.map((item) => item.fileId), ...post.images.map((item) => item.fileId)]), ...CONTENT_IMAGE_IDS];
    if (!all.includes(id)) return notFound();
    return id.startsWith('91')
      ? new HttpResponse(PLACEHOLDER_SVG, { headers: { 'Content-Type': 'image/svg+xml' } })
      : new HttpResponse('시험용 첨부 문서입니다.', { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  }),
];