// 결제 결과. 성공·실패·결과 확인 중·기한 만료를 서버가 판정한 신청 표시 상태로 나누어 보여 준다
import { useQuery } from '@tanstack/react-query';
import { Link, Navigate, useParams } from 'react-router-dom';
import { applicationQuery, sessionQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';
import { ApplicationFacts } from './ApplicationFacts';

type Kind = 'success' | 'failed' | 'unknown' | 'expired';

const CONTENT: Record<Kind, { title: string; message: string }> = {
  success: { title: '결제 완료', message: '수강료 결제가 완료되었습니다.' },
  failed: {
    title: '결제 실패',
    message: '결제를 완료하지 못했습니다. 기한이 남아 있으면 다시 결제하실 수 있습니다.',
  },
  unknown: {
    title: '결제 결과 확인 중',
    message: '승인 결과를 확인하고 있습니다. 확인 전 재결제와 자리 반환이 중단됩니다.',
  },
  expired: { title: '결제기한 만료', message: '결제기한이 지나 신청이 만료되었습니다.' },
};

const KIND_BY_STATE: Record<string, Kind | undefined> = {
  CONFIRMED: 'success',
  PAYMENT_FAILED: 'failed',
  PAYMENT_UNKNOWN: 'unknown',
  EXPIRED: 'expired',
};

export function PaymentResultPage() {
  const { applicationId = '' } = useParams();
  const query = useQuery(applicationQuery(applicationId));
  const session = useQuery(sessionQuery);
  const application = query.data;
  const kind = application ? KIND_BY_STATE[application.displayState] : undefined;
  usePageTitle(kind ? CONTENT[kind].title : '결제 결과');

  if (!application) return <QueryFallback query={query} what="결제 결과" />;
  if (!kind) {
    // 아직 결제 전이면 결제 화면으로, 그 밖의 상태는 신청 상세가 맡는다.
    const to = application.displayState === 'PAYMENT_DUE' ? `/payment/${applicationId}` : `/me/applications/${applicationId}`;
    return <Navigate to={to} replace />;
  }

  const { title, message } = CONTENT[kind];
  const detail = `/me/applications/${application.applicationId}`;

  return (
    <ServicePage title={title} crumbs={[{ label: '회원서비스' }, { label: title }]}>
      <div className="proto">
        <div className="proto-result">
          <h2>{title}</h2>
          <p>{message}</p>
        </div>
        <ApplicationFacts application={application} applicantName={session.data?.member?.name} />
        <div className="proto-actions">
          {kind === 'failed' && application.canPay ? (
            <Link className="button" to={`/payment/${application.applicationId}`}>
              다시 결제하기
            </Link>
          ) : null}
          {kind === 'expired' ? (
            <Link className="button" to={`/apply/${application.course.courseId}`}>
              다시 신청하기
            </Link>
          ) : null}
          {kind === 'unknown' ? (
            <button className="button" type="button" disabled={query.isFetching} onClick={() => void query.refetch()}>
              결과 다시 확인
            </button>
          ) : null}
          <Link className="button secondary" to={kind === 'expired' ? '/me/applications' : detail}>
            {kind === 'expired' ? '신청내역' : '신청 상세'}
          </Link>
          {kind === 'success' && application.paymentId ? (
            <Link className="button secondary" to={`/me/receipts/${application.paymentId}`}>
              영수증
            </Link>
          ) : null}
          {kind === 'success' && application.canRequestRefund ? (
            <Link className="button secondary" to={`${detail}/refund`}>
              환불신청
            </Link>
          ) : null}
        </div>
      </div>
    </ServicePage>
  );
}
