// 관리자 게시판 설정과 게시물 관리를 흉내 내는 모의 서버. 회원이 쓰는 게시판·사용중지 게시판 규칙과 논리 삭제를 서버가 정하는 대로 따른다
import type { Schemas } from '@jori/api-client';
import { HttpResponse, http } from 'msw';
import { apiError, currentAdminName, denyCsrf, denyUnless } from './auth';

type Board = Schemas['BoardSetting'];
type Post = Schemas['AdminPost'];
type BoardKey = Schemas['BoardKey'];

const pid = (n: number) => `17${String(n).padStart(20, '0')}`;
const PAGE_SIZE = 20;

interface State {
  boards: Array<Omit<Board, 'postCount'>>;
  posts: Post[];
  seq: number;
  idempotent: Map<string, { fingerprint: string; body: Post }>;
}

function initialState(): State {
  const board = (boardKey: BoardKey, name: string, memberWrite: boolean, answerEnabled: boolean, attachEnabled: boolean, allowPrivate = false) => ({ boardKey, name, memberWrite, answerEnabled, attachEnabled, allowPrivate, inUse: true, version: 1 });
  const post = (n: number, boardKey: BoardKey, title: string, registeredOn: string, extra: Partial<Post> = {}): Post => ({
    postId: pid(n), boardKey, title, authorName: '김관리', pinned: false, registeredOn, content: `${title}\n\n자세한 내용은 센터로 문의해 주세요.`,
    periodStart: null, periodEnd: null, memberAuthored: false, canEditContent: true, version: 1, ...extra,
  });
  return {
    boards: [
      board('notice', '공지사항', false, false, true),
      board('news', '기관소식', false, false, true),
      board('resources', '자료실', false, false, true),
      board('gallery', '센터 갤러리', false, false, true),
      board('faq', '자주하는 질문', false, false, false),
      board('qna', '질문과 답변', true, true, true, true),
      board('review', '수강후기', true, false, true),
    ],
    posts: [
      post(1, 'notice', '2026년 4분기 수강 안내', '2026-09-01', { pinned: true }),
      post(2, 'notice', '휴관일 안내', '2026-10-20'),
      post(3, 'notice', '시설 점검 안내', '2026-10-28'),
      post(4, 'news', '조리읍 주민자치센터 개강식 개최', '2026-10-01'),
      post(5, 'news', '문화 행사 소식', '2026-10-15'),
      post(6, 'resources', '수강신청 안내서', '2026-09-05'),
      post(7, 'faq', '결제기한은 얼마나 되나요?', '2026-09-03'),
      post(8, 'qna', '결제 확인 문의', '2026-10-22', { authorName: '김○○', memberAuthored: true, canEditContent: false }),
      post(9, 'review', '요가 수업 후기', '2026-10-25', { authorName: '이○○', memberAuthored: true, canEditContent: false }),
    ],
    seq: 20,
    idempotent: new Map(),
  };
}

let state = initialState();

/** 시험 사이에 게시판 설정과 게시물을 처음 상태로 되돌린다. */
/** 첨부 모의 서버가 소유 게시물을 확인할 때 쓰는 제목. 없으면 빈 문자열이다. */
export const mockPostTitle = (postId: string): string => state.posts.find((post) => post.postId === postId)?.title ?? '';

export function resetMockBoards(): void {
  state = initialState();
}

const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
const withCount = (board: State['boards'][number]): Board => ({ ...board, postCount: state.posts.filter((item) => item.boardKey === board.boardKey).length });
const findPost = (id: unknown) => state.posts.find((item) => item.postId === id);
const summary = (post: Post): Schemas['AdminPostSummary'] => ({ postId: post.postId, boardKey: post.boardKey, title: post.title, authorName: post.authorName, pinned: post.pinned, registeredOn: post.registeredOn });

function validateBoardForWrite(boardKey: BoardKey): Record<string, string> | null {
  const board = state.boards.find((item) => item.boardKey === boardKey);
  if (!board) return { boardKey: '게시판을 찾을 수 없습니다.' };
  if (board.memberWrite) return { boardKey: '회원이 작성하는 게시판에는 관리자가 새 글을 쓸 수 없습니다.' };
  if (!board.inUse) return { boardKey: '사용을 중지한 게시판입니다.' };
  return null;
}

function validatePeriod(body: Schemas['AdminPostWrite']): Record<string, string> | null {
  if (body.periodStart && body.periodEnd && body.periodEnd <= body.periodStart) return { periodEnd: '게시 종료는 시작 이후여야 합니다.' };
  return null;
}

export const boardHandlers = [
  http.get('/api/admin/v1/boards', () => {
    const denied = denyUnless('AU.BBS_W', 'AU.POST_W');
    if (denied) return denied;
    return HttpResponse.json({ items: state.boards.map(withCount) });
  }),

  http.put('/api/admin/v1/boards/:boardKey', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.BBS_W');
    if (denied) return denied;
    const board = state.boards.find((item) => item.boardKey === params.boardKey);
    if (!board) return apiError('NOT_FOUND');
    const { version, ...body } = (await request.json()) as Schemas['BoardSettingUpdate'];
    if (version !== board.version) return apiError('VERSION_CONFLICT');
    Object.assign(board, body, { version: board.version + 1 });
    return HttpResponse.json(withCount(board));
  }),

  http.get('/api/admin/v1/posts', ({ request }) => {
    const denied = denyUnless('AU.POST_W');
    if (denied) return denied;
    const params = new URL(request.url).searchParams;
    const q = params.get('q')?.trim();
    const rows = state.posts
      .filter((post) => (!params.get('board') || post.boardKey === params.get('board')) && (!q || post.title.includes(q)))
      .sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.registeredOn.localeCompare(a.registeredOn) || b.postId.localeCompare(a.postId));
    const page = Number(params.get('page') ?? 1);
    const size = Number(params.get('size') ?? PAGE_SIZE);
    return HttpResponse.json({ items: rows.slice((page - 1) * size, page * size).map(summary), page, size, total: rows.length, criteria: { basisAt: new Date().toISOString(), description: null } });
  }),

  http.post('/api/admin/v1/posts', async ({ request }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.POST_W');
    if (denied) return denied;
    const body = (await request.json()) as Schemas['AdminPostWrite'];
    const key = request.headers.get('Idempotency-Key');
    const found = key ? state.idempotent.get(key) : undefined;
    if (found) return found.fingerprint === JSON.stringify(body) ? HttpResponse.json(found.body, { status: 201 }) : apiError('IDEMPOTENCY_CONFLICT');
    const fields = validateBoardForWrite(body.boardKey) ?? validatePeriod(body);
    if (fields) return apiError('RULE_REJECTED', fields);
    state.seq += 1;
    const created: Post = {
      postId: pid(state.seq), boardKey: body.boardKey, title: body.title.trim(), authorName: currentAdminName(), pinned: body.pinned, registeredOn: today(),
      content: body.content, periodStart: body.periodStart ?? null, periodEnd: body.periodEnd ?? null, memberAuthored: false, canEditContent: true, version: 1,
    };
    state.posts.push(created);
    if (key) state.idempotent.set(key, { fingerprint: JSON.stringify(body), body: created });
    return HttpResponse.json(created, { status: 201 });
  }),

  http.get('/api/admin/v1/posts/:postId', ({ params }) => {
    const denied = denyUnless('AU.POST_W');
    if (denied) return denied;
    const post = findPost(params.postId);
    return post ? HttpResponse.json(post) : apiError('NOT_FOUND');
  }),

  http.put('/api/admin/v1/posts/:postId', async ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.POST_W');
    if (denied) return denied;
    const post = findPost(params.postId);
    if (!post) return apiError('NOT_FOUND');
    const { version, ...body } = (await request.json()) as Schemas['AdminPostUpdate'];
    if (version !== post.version) return apiError('VERSION_CONFLICT');
    if (!post.canEditContent) return apiError('RULE_REJECTED', { content: '회원이 쓴 글은 관리자가 고칠 수 없습니다.' });
    const fields = (body.boardKey !== post.boardKey ? { boardKey: '게시판은 바꿀 수 없습니다.' } : null) ?? validatePeriod(body);
    if (fields) return apiError('RULE_REJECTED', fields);
    Object.assign(post, { title: body.title.trim(), content: body.content, pinned: body.pinned, periodStart: body.periodStart ?? null, periodEnd: body.periodEnd ?? null, version: post.version + 1 });
    return HttpResponse.json(post);
  }),

  http.delete('/api/admin/v1/posts/:postId', ({ request, params }) => {
    const denied = denyCsrf(request) ?? denyUnless('AU.POST_W');
    if (denied) return denied;
    const index = state.posts.findIndex((item) => item.postId === params.postId);
    if (index < 0) return apiError('NOT_FOUND');
    state.posts.splice(index, 1);
    return new HttpResponse(null, { status: 204 });
  }),
];