// 감면 심사 내역. 신청한 사전심사의 기수·유형·상태를 보이고 신청과 상세로 잇는다 (화면설계서 S12, 마이페이지)
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { myReductionsQuery, reductionOptionsQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';
import { REDUCTION_STATUS_LABEL, REDUCTION_TYPE_LABEL } from './labels';

const TITLE = '감면 심사';

export function MyReductionsPage() {
  usePageTitle(TITLE);
  const query = useQuery(myReductionsQuery);
  const options = useQuery(reductionOptionsQuery);
  const data = query.data;
  if (!data) return <QueryFallback query={query} what="감면 심사 내역" />;

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: TITLE }]}>
      <div className="proto">
        <p className="proto-hint">조리읍 거주가 확인된 회원 본인이 기수마다 신청해 심사를 받습니다. 승인된 감면은 기수당 1강좌에 적용되며, 금액은 서버가 정합니다.</p>
        {data.items.length === 0 ? (
          <div className="empty-state">
            <h3>신청한 감면 심사가 없습니다.</h3>
          </div>
        ) : (
          data.items.map((item) => (
            <section key={item.reviewId}>
              <h2>
                {item.cycleName} · {REDUCTION_TYPE_LABEL[item.reductionType]}
              </h2>
              <dl className="proto-info">
                <div>
                  <dt>신청일</dt>
                  <dd>{item.appliedOn}</dd>
                </div>
                <div>
                  <dt>증빙</dt>
                  <dd>{item.evidenceCount}건</dd>
                </div>
                <div>
                  <dt>심사 상태</dt>
                  <dd>
                    <span role="status">{REDUCTION_STATUS_LABEL[item.status]}</span>
                  </dd>
                </div>
              </dl>
              <div className="proto-actions">
                <Link className="button secondary" to={`/me/reductions/${item.reviewId}`}>
                  상세 보기
                </Link>
              </div>
            </section>
          ))
        )}
        <div className="proto-actions">
          {options.data?.canApply ? (
            <Link className="button" to="/me/reductions/new">
              감면 신청
            </Link>
          ) : (
            options.data && <p className="proto-hint">{options.data.blockReason ?? '지금은 감면을 신청할 수 없습니다.'}</p>
          )}
        </div>
      </div>
    </ServicePage>
  );
}