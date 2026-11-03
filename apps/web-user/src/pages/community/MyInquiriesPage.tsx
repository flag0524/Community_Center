// 내 문의. 내가 쓴 문의를 제목과 처리 상태로 보인다
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { inquiryListQuery } from '../../api/queries';
import { Pager } from '../../components/Pager';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';
import { INQUIRY_STATUS_LABEL } from './labels';

const TITLE = '내 문의';

export function MyInquiriesPage() {
  usePageTitle(TITLE);
  const [searchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const query = useQuery(inquiryListQuery(page, true));
  const data = query.data;
  if (!data) return <QueryFallback query={query} what="내 문의" />;

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: TITLE }]}>
      <div className="proto">
        {data.items.length === 0 ? (
          <div className="empty-state">
            <h3>작성한 문의가 없습니다.</h3>
          </div>
        ) : (
          <div className="board-list">
            {data.items.map((item) => (
              <Link key={item.postId} className="list-row" to={`/board/qna/${item.postId}`}>
                <strong>{item.title}</strong>
                <span>{INQUIRY_STATUS_LABEL[item.status]}</span>
              </Link>
            ))}
          </div>
        )}
        <Pager
          page={data.page}
          totalPages={Math.ceil(data.total / data.size)}
          hrefFor={(next) => (next > 1 ? `/me/inquiries?page=${next}` : '/me/inquiries')}
        />
        <div className="proto-actions">
          <Link className="button" to="/board/qna/write">
            문의 작성
          </Link>
          <Link className="button secondary" to="/me/applications">
            수강신청내역
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}