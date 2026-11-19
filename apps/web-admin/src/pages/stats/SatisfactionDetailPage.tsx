// 강좌 만족도 집계자료 상세 화면. 문항별 선택 집계를 그대로 보이고 검토 전 자료는 승인 담당자가 두 번 확인해 승인하거나 반려한다 (ADM-DSH-002 집계자료)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { decideSatisfactionSource, type SatisfactionDetail } from '../../api/satisfactionSources';
import { satisfactionSourceQuery } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { RESPONSE_TYPE, STATS_SOURCE_STATE } from '../../lib/labels';
import { isStateConflict } from '../../lib/messages';
import { useHasAuthority } from '../../layout/menu';

export function SatisfactionDetailPage() {
  const { sourceId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(satisfactionSourceQuery(sourceId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return <SatisfactionView key={data.sourceId} source={data} />;
}

function SatisfactionView({ source }: { source: SatisfactionDetail }) {
  const queryClient = useQueryClient();
  const canDecide = useHasAuthority('AU.GRANT_W');
  const mutation = useMutation({
    mutationFn: (action: 'approve' | 'reject') => decideSatisfactionSource(source.sourceId, action),
    onSuccess: (result) => {
      queryClient.setQueryData(satisfactionSourceQuery(result.sourceId).queryKey, result);
      void queryClient.invalidateQueries({ queryKey: ['satisfaction-sources', 'list'] });
      void queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
    onError: (error) => {
      // 다른 담당자가 먼저 결정했다. 최신 상태를 다시 읽는다.
      if (isStateConflict(error)) void queryClient.invalidateQueries({ queryKey: ['satisfaction-sources'] });
    },
  });
  const target = `${source.courseName} ${source.datasetId} 버전 ${source.version}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>만족도 집계자료 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>강좌</dt>
        <dd>{source.courseName}</dd>
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
        <dt>조사 기간</dt>
        <dd>{source.periodStart ?? '-'} ~ {source.periodEnd ?? '-'}</dd>
        <dt>전체 응답자</dt>
        <dd>{source.respondents.toLocaleString('ko-KR')}명</dd>
        <dt>집계 기준</dt>
        <dd className="adm-pre">{source.criteria}</dd>
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
        <Link className="adm-button secondary" to="/satisfaction-sources">
          목록
        </Link>
      </div>
      {source.state === 'WAIT' && canDecide && <p className="adm-notice">승인하면 만족도 통계에 보이는 최신 버전이 되고, 승인한 뒤에는 고칠 수 없습니다.</p>}

      {source.questions.map((question) => (
        <section key={question.questionId}>
          <h2 className="adm-section">
            {question.name} ({RESPONSE_TYPE[question.type]})
          </h2>
          <p className="adm-notice">
            유효응답자 {question.respondents.toLocaleString('ko-KR')}명
            {question.minScore != null && question.maxScore != null ? ` · 점수 범위 ${Number(question.minScore)}~${Number(question.maxScore)}` : ''} · 집계 기준: {question.criteria}
          </p>
          <TableWrap label={`${question.name} 선택 집계`}>
            <table>
              <thead>
                <tr>
                  <th scope="col">선택 항목</th>
                  <th scope="col">응답 수</th>
                  <th scope="col">점수</th>
                </tr>
              </thead>
              <tbody>
                {question.options.map((option) => (
                  <tr key={option.optionId}>
                    <td>{option.name}</td>
                    <td>{option.count.toLocaleString('ko-KR')}명</td>
                    <td>{option.score == null ? '-' : Number(option.score)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </section>
      ))}
    </>
  );
}
