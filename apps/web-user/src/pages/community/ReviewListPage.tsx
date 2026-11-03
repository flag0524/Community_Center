// 수강후기 목록. 누구나 보고 제목으로 검색한다. 작성은 로그인한 수강확정 회원만이다
import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { reviewListQuery } from '../../api/queries';
import { Pager } from '../../components/Pager';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { formatDate } from '../../lib/format';
import { toQueryString } from '../../lib/queryString';
import { usePageTitle } from '../../lib/usePageTitle';
import { COMMUNITY_GROUP_TITLE } from '../board/boards';

const TITLE = '수강후기';

export function ReviewListPage() {
  usePageTitle(TITLE);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const q = searchParams.get('q')?.trim() || undefined;
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const [text, setText] = useState(q ?? '');
  const query = useQuery(reviewListQuery({ q, page }));
  const group = NAV_GROUPS.find((item) => item.title === COMMUNITY_GROUP_TITLE)!;
  const data = query.data;

  function search(event: FormEvent) {
    event.preventDefault();
    navigate(`/board/review${toQueryString({ q: text.trim() || undefined })}`);
  }

  return (
    <SubLayout group={group} title={TITLE} subtitle="" crumbs={[{ label: group.title }, { label: TITLE }]}>
      <form className="toolbar" role="search" aria-label="수강후기 검색" onSubmit={search}>
        <label>
          제목으로 검색
          <input name="q" type="search" placeholder="검색어를 입력해 주세요" value={text} onChange={(event) => setText(event.target.value)} />
        </label>
        <button className="button" type="submit">
          검색
        </button>
      </form>
      {!data ? (
        <QueryFallback query={query} what="수강후기" />
      ) : data.items.length === 0 ? (
        <div className="empty-state">
          <h3>{q ? '검색 결과가 없습니다.' : '등록된 후기가 없습니다.'}</h3>
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <table className="data-table" aria-label="수강후기 목록">
              <thead>
                <tr>
                  <th scope="col">제목</th>
                  <th scope="col">등록일</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.postId}>
                    <td>
                      <Link to={`/board/review/${item.postId}`}>{item.title}</Link>
                    </td>
                    <td>{formatDate(item.publishedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager
            page={data.page}
            totalPages={Math.ceil(data.total / data.size)}
            hrefFor={(next) => `/board/review${toQueryString({ q, page: next > 1 ? next : undefined })}`}
          />
        </>
      )}
      <div className="button-row">
        <Link className="button" to="/board/review/write">
          수강후기 작성
        </Link>
        <Link className="button secondary" to="/me/reviews">
          내 후기 확인
        </Link>
      </div>
    </SubLayout>
  );
}