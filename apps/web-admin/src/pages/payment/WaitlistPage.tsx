// 대기·자리 배정 화면. 강좌별 정원·점유·대기 수와 최근 승격 시각을 보인다. 수동 승격은 없다 (ADM-PAY-002)
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { waitlistQuery } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';

const PAGE_SIZE = 20;

export function WaitlistPage() {
  const [params] = useSearchParams();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const { data, isPending, isError, error } = useQuery(waitlistQuery(page));

  return (
    <>
      <div className="adm-page-heading">
        <h1>대기·자리 배정</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>강좌별 대기 현황</h2>
        </div>
        {isPending && <p role="status">불러오는 중입니다.</p>}
        {isError && <p role="alert">{errorMessage(error)}</p>}
        {data && (
          <>
            <ResultCount total={data.total} />
            <TableWrap label="강좌별 대기 현황">
              <table>
                <thead>
                  <tr>
                    <th scope="col">강좌</th>
                    <th scope="col">정원</th>
                    <th scope="col">점유</th>
                    <th scope="col">대기 수</th>
                    <th scope="col">다음 대기 순번</th>
                    <th scope="col">최근 승격 시각</th>
                    <th scope="col">관리</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row) => (
                    <tr key={row.courseId}>
                      <td>
                        <Link to={`/pay/waitlist/${row.courseId}`}>{row.courseName}</Link>
                      </td>
                      <td>{row.capacity}</td>
                      <td>{row.occupied}</td>
                      <td>{row.waitCount}</td>
                      <td>{row.nextWaitOrder === null ? '-' : `${row.nextWaitOrder}번`}</td>
                      <td>{row.lastPromotedAt ? kstDateTime(row.lastPromotedAt) : '-'}</td>
                      <td>
                        <Link className="adm-button secondary" to={`/pay/waitlist/${row.courseId}`} aria-label={`상세 (${row.courseName})`}>
                          상세
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            <AdminPager page={page} total={data.total} size={PAGE_SIZE} hrefFor={(next) => `/pay/waitlist?page=${next}`} />
          </>
        )}
        <p className="adm-notice">자리는 비는 즉시 대기 순서대로 자동 배정됩니다. 수동 승격은 없습니다.</p>
      </section>
    </>
  );
}
