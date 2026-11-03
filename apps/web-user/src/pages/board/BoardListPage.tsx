// 게시판 목록. 공지·자료실은 표, 기관소식은 줄 목록, 갤러리는 카드, 자주하는 질문은 펼침 항목으로 그린다
import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { postListQuery, type PostSummary } from '../../api/queries';
import { Pager } from '../../components/Pager';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { formatDate } from '../../lib/format';
import { toQueryString } from '../../lib/queryString';
import { usePageTitle } from '../../lib/usePageTitle';
import { BOARDS, COMMUNITY_GROUP_TITLE, fileUrl, paragraphs, type ReadBoardKey } from './boards';

const SEARCHABLE: ReadBoardKey[] = ['notice', 'resources'];

function Arrow() {
  return <span aria-hidden="true"> →</span>;
}

function NoticeTable({ board, items }: { board: ReadBoardKey; items: PostSummary[] }) {
  return (
    <div className="table-wrap">
      <table className="data-table" aria-label={`${BOARDS[board].title} 목록`}>
        <thead>
          <tr>
            <th scope="col">구분</th>
            <th scope="col">제목</th>
            <th scope="col">등록일</th>
          </tr>
        </thead>
        <tbody>
          {items.map((post) => (
            <tr key={post.postId}>
              <td>{post.pinned ? '공지' : '일반'}</td>
              <td>
                <Link to={`${BOARDS[board].path}/${post.postId}`}>
                  {post.title}
                  <Arrow />
                </Link>
              </td>
              <td>{formatDate(post.publishedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ResourceTable({ items }: { items: PostSummary[] }) {
  return (
    <div className="table-wrap">
      <table className="data-table" aria-label="자료실 목록">
        <thead>
          <tr>
            <th scope="col">제목</th>
            <th scope="col">등록일</th>
            <th scope="col">자료</th>
          </tr>
        </thead>
        <tbody>
          {items.map((post) => (
            <tr key={post.postId}>
              <td>
                <Link to={`${BOARDS.resources.path}/${post.postId}`}>
                  {post.title}
                  <Arrow />
                </Link>
              </td>
              <td>{formatDate(post.publishedAt)}</td>
              <td>
                {post.primaryFile ? (
                  // 상세(제목)와 자료 보기(첨부)는 다른 동작이다. 자료는 새 창에서 연다.
                  <a href={fileUrl(post.primaryFile.fileId)} target="_blank" rel="noopener noreferrer">
                    자료 보기
                    <Arrow />
                  </a>
                ) : (
                  '-'
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NewsList({ items }: { items: PostSummary[] }) {
  return (
    <>
      <h2 className="section-heading">센터 소식</h2>
      <div className="board-list">
        {items.map((post) => (
          <Link key={post.postId} className="list-row" to={`${BOARDS.news.path}/${post.postId}`}>
            <span>{post.title}</span>
            <time dateTime={post.publishedAt}>{formatDate(post.publishedAt)}</time>
          </Link>
        ))}
      </div>
    </>
  );
}

function GalleryList({ items }: { items: PostSummary[] }) {
  return (
    <>
      {items.map((post) => {
        const to = `${BOARDS.gallery.path}/${post.postId}`;
        return (
          <article key={post.postId}>
            {post.thumbnail ? (
              <Link to={to}>
                <img src={fileUrl(post.thumbnail.fileId)} alt={post.thumbnail.alt} />
              </Link>
            ) : null}
            <h2>
              <Link to={to}>{post.title}</Link>
            </h2>
            <p>
              <time dateTime={post.publishedAt}>{formatDate(post.publishedAt)}</time>
            </p>
          </article>
        );
      })}
    </>
  );
}

function FaqList({ items }: { items: PostSummary[] }) {
  return (
    <div className="faq-list guide-list">
      {items.map((post, index) => (
        // 첫 항목만 펼쳐 둔다(FN-020).
        <details key={post.postId} open={index === 0}>
          <summary>{post.title}</summary>
          <div>
            {paragraphs(post.body ?? '').map((text) => (
              <p key={text}>{text}</p>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

export function BoardListPage({ board }: { board: ReadBoardKey }) {
  const config = BOARDS[board];
  usePageTitle(config.title);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const q = searchParams.get('q')?.trim() || undefined;
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const [text, setText] = useState(q ?? '');
  const query = useQuery(postListQuery(board, { q, page }));
  const group = NAV_GROUPS.find((item) => item.title === COMMUNITY_GROUP_TITLE)!;
  const data = query.data;

  function search(event: FormEvent) {
    event.preventDefault();
    navigate(`${config.path}${toQueryString({ q: text.trim() || undefined })}`);
  }

  return (
    <SubLayout group={group} title={config.title} subtitle="" crumbs={[{ label: group.title }, { label: config.title }]}>
      {SEARCHABLE.includes(board) ? (
        <form className="toolbar" role="search" aria-label={`${config.title} 검색`} onSubmit={search}>
          <label>
            제목으로 검색
            <input name="q" type="search" placeholder="검색어를 입력해 주세요" value={text} onChange={(event) => setText(event.target.value)} />
          </label>
          <button className="button" type="submit">
            검색
          </button>
        </form>
      ) : null}
      {!data ? (
        <QueryFallback query={query} what="게시물" />
      ) : data.items.length === 0 ? (
        <div className="empty-state">
          <h3>{q ? '검색 결과가 없습니다.' : '등록된 게시물이 없습니다.'}</h3>
        </div>
      ) : (
        <>
          {board === 'notice' ? <NoticeTable board={board} items={data.items} /> : null}
          {board === 'resources' ? <ResourceTable items={data.items} /> : null}
          {board === 'news' ? <NewsList items={data.items} /> : null}
          {board === 'gallery' ? <GalleryList items={data.items} /> : null}
          {board === 'faq' ? <FaqList items={data.items} /> : null}
          <Pager
            page={data.page}
            totalPages={Math.ceil(data.total / data.size)}
            hrefFor={(next) => `${config.path}${toQueryString({ q, page: next > 1 ? next : undefined })}`}
          />
        </>
      )}
    </SubLayout>
  );
}