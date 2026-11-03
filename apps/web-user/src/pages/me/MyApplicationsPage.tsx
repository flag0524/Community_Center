// 내 수강신청내역. 신청 강좌와 서버가 판정한 신청·결제·환불 상태를 표로 보여 준다
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { myApplicationsQuery } from '../../api/queries';
import { Pager } from '../../components/Pager';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { applicationStateText, paymentStatusText, refundStageText } from '../../lib/applicationLabels';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '수강신청내역';

export function MyApplicationsPage() {
  usePageTitle(TITLE);
  const [searchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const query = useQuery(myApplicationsQuery(page));
  const data = query.data;

  if (!data) return <QueryFallback query={query} what="신청 내역" />;

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: TITLE }]}>
      <div className="proto">
        <h2>신청내역</h2>
        {data.items.length === 0 ? (
          <div className="empty-state">
            <h3>신청 내역이 없습니다.</h3>
            <Link className="button" to="/courses">
              강좌 보기
            </Link>
          </div>
        ) : (
          <>
            <div className="course-table-wrap">
              <table aria-label={TITLE}>
                <thead>
                  <tr>
                    <th scope="col">신청 강좌</th>
                    <th scope="col">신청상태</th>
                    <th scope="col">결제상태</th>
                    <th scope="col">환불상태</th>
                    <th scope="col">확인</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr key={item.applicationId}>
                      <td>{item.course.name}</td>
                      <td>{applicationStateText(item)}</td>
                      <td>{paymentStatusText(item)}</td>
                      <td>{item.refundStage ? refundStageText(item.refundStage) : '-'}</td>
                      <td>
                        {/* 이름이 보이는 글자를 낱말 단위로 포함해야 한다(WCAG 2.5.3). */}
                        <Link to={`/me/applications/${item.applicationId}`} aria-label={`상세 (${item.course.name})`}>
                          상세
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              page={data.page}
              totalPages={Math.ceil(data.total / data.size)}
              hrefFor={(next) => (next > 1 ? `/me/applications?page=${next}` : '/me/applications')}
            />
          </>
        )}
        <div className="proto-actions">
          <Link className="button secondary" to="/me/refunds">
            환불신청 내역
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}