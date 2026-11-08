// 게시물 목록 화면. 게시판을 고르면 그 게시판의 글을 보이고 상단공지가 먼저 나온다 (ADM-MBR-002)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { adminPostListQuery, boardListQuery, type AdminPostParams } from '../../api/queries';
import { CsvButton } from '../../components/CsvButton';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['board', 'q'] as const;

export function PostListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: AdminPostParams = {
    board: (params.get('board') as Schemas['BoardKey'] | null) ?? undefined,
    q: params.get('q') ?? undefined,
    page,
  };
  const list = useQuery(adminPostListQuery(filters));
  const boards = useQuery(boardListQuery);
  const boardName = (key: string) => boards.data?.items.find((board) => board.boardKey === key)?.name ?? key;

  const hrefFor = (next: number) =>
    `/mbr/posts${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>게시물</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>게시물 목록</h2>
          <Link className="adm-button" to="/mbr/posts/new">
            등록
          </Link>
        </div>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="게시물 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const next = Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()]));
            void navigate(`/mbr/posts${toQueryString(next)}`);
          }}
        >
          <label>
            게시판
            <select name="board" defaultValue={filters.board ?? ''}>
              <option value="">전체 게시판</option>
              {boards.data?.items.map((board) => (
                <option key={board.boardKey} value={board.boardKey}>
                  {board.name}
                </option>
              ))}
            </select>
          </label>
          <label className="wide">
            검색어
            <input name="q" defaultValue={filters.q} placeholder="제목" maxLength={100} />
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/mbr/posts">
            조건 지우기
          </Link>
          <CsvButton path="/posts/export.csv" query={toQueryString(Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])))} />
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="게시물 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">제목</th>
                    <th scope="col">게시판</th>
                    <th scope="col">작성자</th>
                    <th scope="col">상단공지</th>
                    <th scope="col">등록일</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((post) => (
                    <tr key={post.postId}>
                      <td>
                        <Link to={`/mbr/posts/${post.postId}`}>{post.title}</Link>
                      </td>
                      <td>{boardName(post.boardKey)}</td>
                      <td>{post.authorName}</td>
                      <td>{post.pinned ? '상단공지' : '-'}</td>
                      <td>{post.registeredOn}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 게시물이 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}
