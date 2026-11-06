// 알림 상세 화면. 확정 문안과 수신 대상별 결과를 보이고 실패·확인 중인 건을 따로 모아 다시 확인할 수 있게 한다 (ADM-SYS-001)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation, useParams } from 'react-router-dom';
import { smsQuery } from '../../api/queries';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { SMS_KIND, SMS_SCOPE, SMS_TARGET_STATE } from '../../lib/labels';

function TargetTable({ label, rows }: { label: string; rows: Schemas['SmsTargetRow'][] }) {
  return (
    <TableWrap label={label}>
      <table>
        <thead>
          <tr>
            <th scope="col">수신자</th>
            <th scope="col">수신번호</th>
            <th scope="col">상태</th>
            <th scope="col">시도</th>
            <th scope="col">실패 사유</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((target) => (
            <tr key={target.targetId}>
              <td>{target.name}</td>
              <td>{target.phone}</td>
              <td>{SMS_TARGET_STATE[target.state]}</td>
              <td>{target.attempts}회</td>
              <td>{target.failReason ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

export function SmsDetailPage() {
  const { smsId = '' } = useParams();
  const sent = (useLocation().state as { sent?: boolean } | null)?.sent === true;
  const { data, isPending, isError, error } = useQuery(smsQuery(smsId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  const attention = data.targets.filter((target) => target.state === 'FAIL' || target.state === 'UNKNOWN');

  return (
    <>
      <div className="adm-page-heading">
        <h1>알림 상세</h1>
      </div>
      {sent && (
        <p className="adm-message" role="status">
          발송 요청을 접수했습니다. 발송 결과는 잠시 뒤 이 화면에서 확인할 수 있습니다.
        </p>
      )}
      <dl className="adm-facts">
        <dt>요청일시</dt>
        <dd>{kstDateTime(data.requestedAt)}</dd>
        <dt>유형</dt>
        <dd>
          {SMS_KIND[data.kind]} · {SMS_SCOPE[data.scope]}
        </dd>
        <dt>요청자</dt>
        <dd>{data.requestedBy}</dd>
        {data.courseNames.length > 0 && (
          <>
            <dt>선택 강좌</dt>
            <dd>{data.courseNames.join(', ')}</dd>
          </>
        )}
        <dt>대상 수</dt>
        <dd>{data.targetCount}</dd>
        <dt>성공 · 실패 · 확인중</dt>
        <dd>
          {data.sent} · {data.failed} · {data.unknown}
        </dd>
        <dt>문안</dt>
        <dd className="adm-pre">{data.content}</dd>
      </dl>

      <h2 className="adm-section">확인이 필요한 건</h2>
      {attention.length > 0 ? <TargetTable label="확인이 필요한 건" rows={attention} /> : <p>실패하거나 확인 중인 건이 없습니다.</p>}

      <h2 className="adm-section">수신 대상별 결과</h2>
      {data.targetsTruncated && <p className="adm-notice">수신 대상이 200건을 넘어 앞의 200건만 보입니다.</p>}
      <TargetTable label="수신 대상별 결과" rows={data.targets} />
      <div className="adm-actions">
        <Link className="adm-button secondary" to={`/sys/sms?kind=${data.kind}`}>
          목록
        </Link>
      </div>
    </>
  );
}