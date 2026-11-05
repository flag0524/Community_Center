// 대기·자리 배정 상세 화면. 대기자 순번 목록과 자동 승격 이력(배정시각·결제기한·문자 결과)을 조회만 한다 (ADM-PAY-002P)
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { waitlistDetailQuery } from '../../api/queries';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { SMS_RESULT } from '../../lib/labels';

export function WaitlistDetailPage() {
  const { courseId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(waitlistDetailQuery(courseId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;

  return (
    <>
      <div className="adm-page-heading">
        <h1>대기·자리 배정 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>강좌</dt>
        <dd>{data.courseName}</dd>
        <dt>정원 / 점유 / 대기</dt>
        <dd>
          {data.capacity} / {data.occupied} / {data.waitCount}
        </dd>
        <dt>최근 승격 시각</dt>
        <dd>{data.lastPromotedAt ? kstDateTime(data.lastPromotedAt) : '-'}</dd>
      </dl>

      <h2 className="adm-section">대기자 순번</h2>
      {data.waiters.length > 0 ? (
        <TableWrap label="대기자 순번">
          <table>
            <thead>
              <tr>
                <th scope="col">순번</th>
                <th scope="col">신청번호</th>
                <th scope="col">신청자</th>
                <th scope="col">접수시각</th>
              </tr>
            </thead>
            <tbody>
              {data.waiters.map((waiter) => (
                <tr key={waiter.applicationNo}>
                  <td>{waiter.order}</td>
                  <td>{waiter.applicationNo}</td>
                  <td>{waiter.applicantName}</td>
                  <td>{kstDateTime(waiter.appliedAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>대기자가 없습니다.</p>
      )}

      <h2 className="adm-section">승격 이력</h2>
      {data.promotions.length > 0 ? (
        <TableWrap label="승격 이력">
          <table>
            <thead>
              <tr>
                <th scope="col">배정시각</th>
                <th scope="col">신청번호</th>
                <th scope="col">결제기한</th>
                <th scope="col">문자 결과</th>
              </tr>
            </thead>
            <tbody>
              {data.promotions.map((promotion) => (
                <tr key={promotion.applicationNo}>
                  <td>{kstDateTime(promotion.promotedAt)}</td>
                  <td>{promotion.applicationNo}</td>
                  <td>{kstDateTime(promotion.deadlineAt)}</td>
                  <td>{SMS_RESULT[promotion.smsResult]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>승격 이력이 없습니다.</p>
      )}
      <p className="adm-notice">자동 배정만 있고 수동 승격 버튼은 없습니다. 결제기한은 자리 배정 시각에서 600초입니다.</p>
      <div className="adm-actions">
        <Link className="adm-button secondary" to="/pay/waitlist">
          목록
        </Link>
      </div>
    </>
  );
}
