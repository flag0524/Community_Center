// 연령·성별 집계자료 상세 화면. 입력한 표를 그대로 보이고 검토 대기 자료는 승인 담당자가 두 번 확인해 승인하거나 반려한다 (ADM-DSH-002 집계자료)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { decideSource, type SourceDetail } from '../../api/statsSources';
import { statsSourceQuery } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { STATS_SOURCE_STATE } from '../../lib/labels';
import { isStateConflict } from '../../lib/messages';
import { useHasAuthority } from '../../layout/menu';

export function SourceDetailPage() {
  const { sourceId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(statsSourceQuery(sourceId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return <SourceView key={data.sourceId} source={data} />;
}

function SourceView({ source }: { source: SourceDetail }) {
  const queryClient = useQueryClient();
  const canDecide = useHasAuthority('AU.GRANT_W');
  const mutation = useMutation({
    mutationFn: (action: 'approve' | 'reject') => decideSource(source.sourceId, action),
    onSuccess: (result) => {
      queryClient.setQueryData(statsSourceQuery(result.sourceId).queryKey, result);
      void queryClient.invalidateQueries({ queryKey: ['stats-sources', 'list'] });
      void queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
    onError: (error) => {
      // 다른 담당자가 먼저 결정했다. 최신 상태를 다시 읽는다.
      if (isStateConflict(error)) void queryClient.invalidateQueries({ queryKey: ['stats-sources'] });
    },
  });
  const target = `${source.datasetId} 버전 ${source.version}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>집계자료 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>계열</dt>
        <dd>{source.datasetId}</dd>
        <dt>버전</dt>
        <dd>{source.version}</dd>
        <dt>상태</dt>
        <dd>{STATS_SOURCE_STATE[source.state]}</dd>
        <dt>출처</dt>
        <dd>{source.provider}</dd>
        <dt>근거</dt>
        <dd>{source.basisId}</dd>
        <dt>집계 기간</dt>
        <dd>{source.periodStart ?? '-'} ~ {source.periodEnd ?? '-'}</dd>
        <dt>연령 기준일</dt>
        <dd>{source.ageBasisDate ?? '-'}</dd>
        <dt>모집단·중복 처리 기준</dt>
        <dd className="adm-pre">{source.dedupeNote}</dd>
        <dt>등록일시</dt>
        <dd>{kstDateTime(source.registeredAt)}</dd>
        {source.decidedAt && (
          <>
            <dt>결정</dt>
            <dd>
              {source.decidedBy ?? '-'} · {kstDateTime(source.decidedAt)}
            </dd>
          </>
        )}
      </dl>
      {mutation.isError && (
        <p className="adm-message error" role="alert">
          {isStateConflict(mutation.error) ? '이미 다른 담당자가 처리했습니다. 최신 상태를 확인해 주세요.' : errorMessage(mutation.error)}
        </p>
      )}
      <div className="adm-actions">
        {source.state === 'WAIT' && canDecide && (
          <>
            <ConfirmButton label="승인" confirmLabel="정말 승인" target={target} disabled={mutation.isPending} onConfirm={() => mutation.mutate('approve')} />
            <ConfirmButton label="반려" confirmLabel="정말 반려" target={target} disabled={mutation.isPending} onConfirm={() => mutation.mutate('reject')} />
          </>
        )}
        <Link className="adm-button secondary" to="/stats-sources">
          목록
        </Link>
      </div>
      {source.state === 'WAIT' && canDecide && <p className="adm-notice">승인하면 통계에 보이는 최신 버전이 되고, 승인한 뒤에는 고칠 수 없습니다.</p>}

      <h2 className="adm-section">집계 표</h2>
      <TableWrap label="집계 표">
        <table>
          <thead>
            <tr>
              <th scope="col">연령구간</th>
              <th scope="col">하한</th>
              <th scope="col">상한</th>
              <th scope="col">성별 분류</th>
              <th scope="col">인원</th>
            </tr>
          </thead>
          <tbody>
            {source.rows.map((row) => (
              <tr key={`${row.ageGroupId}|${row.genderId}`}>
                <td>{row.ageGroupName}</td>
                <td>{row.lowerAge ?? '-'}</td>
                <td>{row.upperAge ?? '-'}</td>
                <td>{row.genderName}</td>
                <td>{row.count.toLocaleString('ko-KR')}명</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </>
  );
}
