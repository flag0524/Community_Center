// 내 수강후기. 내가 쓴 후기를 제목과 게시 상태로 보인다
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { reviewListQuery } from '../../api/queries';
import { Pager } from '../../components/Pager';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '내 수강후기';

export function MyReviewsPage() {
  usePageTitle(TITLE);
  const [searchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const query = useQuery(reviewListQuery({ page }, true));
  const data = query.data;
  if (!data) return <QueryFallback query={query} what="내 후기" />;

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: TITLE }]}>
      <div className="proto">
        {data.items.length === 0 ? (
          <div className="empty-state">
            <h3>작성한 후기가 없습니다.</h3>
          </div>
        ) : (
          <div className="board-list">
            {data.items.map((item) => (
              <Link key={item.postId} className="list-row" to={`/board/review/${item.postId}`}>
                <strong>{item.title}</strong>
                <span>게시중</span>
              </Link>
            ))}
          </div>
        )}
        <Pager
          page={data.page}
          totalPages={Math.ceil(data.total / data.size)}
          hrefFor={(next) => (next > 1 ? `/me/reviews?page=${next}` : '/me/reviews')}
        />
        <div className="proto-actions">
          <Link className="button" to="/board/review/write">
            후기 작성
          </Link>
          <Link className="button secondary" to="/me/applications">
            수강신청내역
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}