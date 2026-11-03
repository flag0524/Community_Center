// 환불신청 내역. 주민 화면 단계(접수·처리 중·보류·환불완료·반려)와 보류·반려 사유를 보인다
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { myRefundsQuery } from '../../api/queries';
import { Pager } from '../../components/Pager';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { refundStageText } from '../../lib/applicationLabels';
import { formatFee } from '../../lib/course';
import { formatDate } from '../../lib/format';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '환불신청 내역';

export function MyRefundsPage() {
  usePageTitle(TITLE);
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const query = useQuery(myRefundsQuery(page));
  const data = query.data;
  const created = (location.state as { created?: boolean } | null)?.created === true;

  if (!data) return <QueryFallback query={query} what="환불신청 내역" />;

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: TITLE }]}>
      <div className="proto">
        {created ? (
          <div className="proto-result" role="status">
            <h2>환불신청이 접수되었습니다.</h2>
            <p>접수된 사유를 확인하고 있습니다.</p>
          </div>
        ) : null}
        {data.items.length === 0 ? (
          <div className="empty-state">
            <h3>환불신청 내역이 없습니다.</h3>
          </div>
        ) : (
          <>
            <div className="course-table-wrap">
              <table aria-label={TITLE}>
                <thead>
                  <tr>
                    <th scope="col">신청 강좌</th>
                    <th scope="col">환불금액</th>
                    <th scope="col">처리상태</th>
                    <th scope="col">신청일</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr key={item.refundId}>
                      <td>{item.courseName}</td>
                      <td>{formatFee(item.amount)}</td>
                      <td>
                        {refundStageText(item.stage)}
                        {item.reason ? (
                          <>
                            <br />
                            <small>{item.reason}</small>
                          </>
                        ) : null}
                      </td>
                      <td>{formatDate(item.requestedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              page={data.page}
              totalPages={Math.ceil(data.total / data.size)}
              hrefFor={(next) => (next > 1 ? `/me/refunds?page=${next}` : '/me/refunds')}
            />
          </>
        )}
        <div className="proto-actions">
          <Link className="button secondary" to="/me/applications">
            신청내역
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}