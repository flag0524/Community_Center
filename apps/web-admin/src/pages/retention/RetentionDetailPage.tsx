// 보존·파기 상세 화면. 처리하는 항목과 규칙을 보이고 예정일이 지난 자료만 두 번 확인해 실행하며 실행 결과를 감사기록으로 남긴다 (ADM-SYS-005)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { executeRetention, type RetentionDetail } from '../../api/retention';
import { retentionQuery } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { RETENTION_STATE, RETENTION_TARGET } from '../../lib/labels';
import { allFieldMessages, isStateConflict } from '../../lib/messages';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

export function RetentionDetailPage() {
  const { itemId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(retentionQuery(itemId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return <RetentionView key={data.itemId} item={data} />;
}

function RetentionView({ item }: { item: RetentionDetail }) {
  const queryClient = useQueryClient();
  const key = useIdempotencyKey();
  const [done, setDone] = useState<number | null>(null);
  const mutation = useMutation({
    mutationFn: () => executeRetention(item.itemId, item.count, key.current()),
    onSuccess: (result) => {
      key.renew();
      queryClient.setQueryData(retentionQuery(result.itemId).queryKey, result);
      void queryClient.invalidateQueries({ queryKey: ['retention', 'list'] });
      setDone(result.executions[0]?.processed ?? 0);
    },
    onError: (error) => {
      // 확인한 뒤 대상이 바뀌었다. 서버가 다시 센 건수를 보고 다시 확인한다.
      if (isStateConflict(error)) void queryClient.invalidateQueries({ queryKey: ['retention'] });
    },
  });
  const target = RETENTION_TARGET[item.target];

  return (
    <>
      <div className="adm-page-heading">
        <h1>보존·파기 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>대상 유형</dt>
        <dd>{target}</dd>
        <dt>건수</dt>
        <dd>{item.count.toLocaleString('ko-KR')}건</dd>
        <dt>기준일</dt>
        <dd>{item.baseDate ?? '-'}</dd>
        <dt>예정일</dt>
        <dd>{item.dueOn ?? '미정'}</dd>
        <dt>상태</dt>
        <dd>{RETENTION_STATE[item.state]}</dd>
        <dt>보존 규칙</dt>
        <dd className="adm-pre">{item.rule}</dd>
      </dl>
      <h2 className="adm-section">처리 항목</h2>
      <ul className="adm-list">
        {item.fields.map((field) => (
          <li key={field}>{field}</li>
        ))}
      </ul>
      {item.state === 'PERIOD_TBD' && <p className="adm-notice">보존기간이 정해지기 전에는 실행할 수 없습니다.</p>}
      {item.state === 'REVIEW_ONLY' && <p className="adm-notice">이 자료는 검토만 하고 이 화면에서 실행하지 않습니다.</p>}
      {done !== null && (
        <p className="adm-message" role="status">
          실행했습니다. {done.toLocaleString('ko-KR')}건을 처리했습니다.
        </p>
      )}
      {mutation.isError && (
        <p className="adm-message error" role="alert">
          {isStateConflict(mutation.error) ? '확인한 뒤 대상이 바뀌었습니다. 아래 건수를 다시 확인해 주세요.' : allFieldMessages(mutation.error) || errorMessage(mutation.error)}
        </p>
      )}
      <div className="adm-actions">
        {item.canExecute && (
          <>
            <p className="adm-notice">실행하면 되돌릴 수 없습니다. 지금 {item.count.toLocaleString('ko-KR')}건이 대상입니다.</p>
            <ConfirmButton label="실행" confirmLabel="정말 실행" target={`${target} ${item.count}건`} disabled={mutation.isPending} onConfirm={() => mutation.mutate()} />
          </>
        )}
        <Link className="adm-button secondary" to="/sys/retention">
          목록
        </Link>
      </div>

      <h2 className="adm-section">실행 결과 기록</h2>
      {item.executions.length > 0 ? (
        <TableWrap label="실행 결과 기록">
          <table>
            <thead>
              <tr>
                <th scope="col">시각</th>
                <th scope="col">실행자</th>
                <th scope="col">처리 건수</th>
              </tr>
            </thead>
            <tbody>
              {item.executions.map((entry) => (
                <tr key={entry.at}>
                  <td>{kstDateTime(entry.at)}</td>
                  <td>{entry.by}</td>
                  <td>{entry.processed.toLocaleString('ko-KR')}건</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>실행한 기록이 없습니다.</p>
      )}
    </>
  );
}