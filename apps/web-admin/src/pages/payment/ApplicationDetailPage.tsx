// 수강신청 상세 화면. 신청 원장의 상태 변경 이력과 연결 결제·환불, 멱등 재요청 기록을 조회만 한다 (ADM-PAY-001P)
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { adminApplicationQuery } from '../../api/queries';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime, won } from '../../lib/format';
import { APPLICATION_STATUS, DISPLAY_STATE, PAYMENT_METHOD, PAYMENT_STATUS, REFUND_STATUS, REPLAY_OUTCOME } from '../../lib/labels';

export function ApplicationDetailPage() {
  const { applicationId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(adminApplicationQuery(applicationId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;

  return (
    <>
      <div className="adm-page-heading">
        <h1>수강신청 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>신청번호</dt>
        <dd>{data.applicationNo}</dd>
        <dt>강좌</dt>
        <dd>
          {data.courseName} ({data.cycleName})
        </dd>
        <dt>신청자</dt>
        <dd>{data.applicantName}</dd>
        <dt>상태</dt>
        <dd>{DISPLAY_STATE[data.displayState]}</dd>
        {data.waitingOrder !== null && (
          <>
            <dt>대기 순번</dt>
            <dd>{data.waitingOrder}번</dd>
          </>
        )}
        <dt>접수시각</dt>
        <dd>{kstDateTime(data.appliedAt)}</dd>
        <dt>자리 배정</dt>
        <dd>{data.seatAllottedAt ? kstDateTime(data.seatAllottedAt) : '-'}</dd>
        <dt>결제기한</dt>
        <dd>{data.paymentDeadlineAt ? kstDateTime(data.paymentDeadlineAt) : '-'}</dd>
      </dl>

      <h2 className="adm-section">상태 변경 이력</h2>
      <TableWrap label="상태 변경 이력">
        <table>
          <thead>
            <tr>
              <th scope="col">시각</th>
              <th scope="col">이전</th>
              <th scope="col">이후</th>
              <th scope="col">처리자</th>
              <th scope="col">비고</th>
            </tr>
          </thead>
          <tbody>
            {data.history.map((entry) => (
              <tr key={`${entry.at}-${entry.toStatus}`}>
                <td>{kstDateTime(entry.at)}</td>
                <td>{entry.fromStatus ? APPLICATION_STATUS[entry.fromStatus] : '-'}</td>
                <td>{APPLICATION_STATUS[entry.toStatus]}</td>
                <td>{entry.actor}</td>
                <td>{entry.note ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>

      <h2 className="adm-section">연결 결제</h2>
      {data.payment ? (
        <dl className="adm-facts">
          <dt>주문번호</dt>
          <dd>{data.payment.orderNo}</dd>
          <dt>결제수단</dt>
          <dd>{PAYMENT_METHOD[data.payment.method]}</dd>
          <dt>금액</dt>
          <dd>{won(data.payment.amount)}</dd>
          <dt>상태</dt>
          <dd>{PAYMENT_STATUS[data.payment.status]}</dd>
          <dt>승인시각</dt>
          <dd>{data.payment.approvedAt ? kstDateTime(data.payment.approvedAt) : '-'}</dd>
        </dl>
      ) : (
        <p>연결된 결제가 없습니다.</p>
      )}

      <h2 className="adm-section">연결 환불</h2>
      {data.refund ? (
        <dl className="adm-facts">
          <dt>환불번호</dt>
          <dd>{data.refund.refundNo}</dd>
          <dt>금액</dt>
          <dd>{won(data.refund.amount)}</dd>
          <dt>상태</dt>
          <dd>{REFUND_STATUS[data.refund.status]}</dd>
        </dl>
      ) : (
        <p>연결된 환불이 없습니다.</p>
      )}

      <h2 className="adm-section">멱등 재요청 기록</h2>
      {data.replays.length > 0 ? (
        <TableWrap label="멱등 재요청 기록">
          <table>
            <thead>
              <tr>
                <th scope="col">시각</th>
                <th scope="col">처리 결과</th>
              </tr>
            </thead>
            <tbody>
              {data.replays.map((entry) => (
                <tr key={entry.at}>
                  <td>{kstDateTime(entry.at)}</td>
                  <td>{REPLAY_OUTCOME[entry.outcome]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>재요청 기록이 없습니다.</p>
      )}
      <p className="adm-notice">관리자는 신청 상태를 직접 바꿀 수 없습니다. 방문·유선 환불 접수는 환불 화면에서 합니다.</p>
      <div className="adm-actions">
        <Link className="adm-button secondary" to="/pay/applications">
          목록
        </Link>
      </div>
    </>
  );
}
