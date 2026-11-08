// 감면 심사 상세. 심사 결과와 반려 사유를 보이고 접수 상태에서만 증빙을 올리거나 신청을 철회할 수 있다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useLocation, useParams, Link } from 'react-router-dom';
import { withdrawReduction } from '../../api/reductions';
import { myReductionQuery } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { MyFiles } from '../../components/MyFiles';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { errorMessage } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';
import { REDUCTION_STATUS_LABEL, REDUCTION_TYPE_LABEL } from './labels';

const TITLE = '감면 심사 상세';

export function MyReductionDetailPage() {
  usePageTitle(TITLE);
  const { reviewId = '' } = useParams();
  const created = (useLocation().state as { created?: boolean } | null)?.created === true;
  const queryClient = useQueryClient();
  const query = useQuery(myReductionQuery(reviewId));
  const [asking, setAsking] = useState(false);
  const withdraw = useMutation({
    mutationFn: () => withdrawReduction(reviewId),
    onSuccess: (result) => {
      queryClient.setQueryData(myReductionQuery(reviewId).queryKey, result);
      void queryClient.invalidateQueries({ queryKey: ['me', 'reductions'] });
      void queryClient.invalidateQueries({ queryKey: ['my-files'] });
      setAsking(false);
    },
  });
  const data = query.data;
  if (!data) return <QueryFallback query={query} what="감면 심사" />;

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: '감면 심사', to: '/me/reductions' }, { label: TITLE }]}>
      <div className="proto">
        {created && <FormMessage text="신청했습니다. 아래에서 증빙 파일을 올려 주세요." />}
        <dl className="proto-info">
          <div>
            <dt>교육기수</dt>
            <dd>{data.cycleName}</dd>
          </div>
          <div>
            <dt>감면 유형</dt>
            <dd>{REDUCTION_TYPE_LABEL[data.reductionType]}</dd>
          </div>
          <div>
            <dt>신청일</dt>
            <dd>{data.appliedOn}</dd>
          </div>
          <div>
            <dt>심사 상태</dt>
            <dd>
              <span role="status">{REDUCTION_STATUS_LABEL[data.status]}</span>
            </dd>
          </div>
          {data.validUntil && (
            <div>
              <dt>승인 유효 종료일</dt>
              <dd>{data.validUntil}</dd>
            </div>
          )}
          {data.rejectReason && (
            <div>
              <dt>반려 사유</dt>
              <dd>{data.rejectReason}</dd>
            </div>
          )}
        </dl>
        <MyFiles ownerPath={`/me/reduction-reviews/${reviewId}`} label="증빙 파일" />
        {data.status === 'REJECTED' && <p className="proto-hint">반려된 신청은 고칠 수 없습니다. 다시 심사를 받으려면 새로 신청해 주세요.</p>}
        {data.canWithdraw && (
          <div className="proto-actions">
            {asking ? (
              <div className="proto-consent" role="group" aria-label="신청 철회 확인">
                <p>이 신청을 철회할까요? 철회하면 증빙을 더 올릴 수 없고 다시 심사를 받으려면 새로 신청해야 합니다.</p>
                <div className="proto-actions">
                  <button className="button" type="button" disabled={withdraw.isPending} onClick={() => withdraw.mutate()}>
                    철회하기
                  </button>
                  <button className="button secondary" type="button" onClick={() => setAsking(false)}>
                    돌아가기
                  </button>
                </div>
                <FormMessage text={withdraw.isError ? errorMessage(withdraw.error) : ''} error />
              </div>
            ) : (
              <button className="button secondary" type="button" onClick={() => setAsking(true)}>
                신청 철회
              </button>
            )}
          </div>
        )}
        <div className="proto-actions">
          <Link className="button secondary" to="/me/reductions">
            목록
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}