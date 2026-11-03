// 내 수강신청 상세. 서버가 정한 가능 여부(결제·영수증·환불·취소)대로 버튼을 보이고 신청 취소는 한 번 더 확인한다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { cancelApplication } from '../../api/applications';
import { applicationQuery, sessionQuery } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { applicationStateText, refundStageText } from '../../lib/applicationLabels';
import { errorMessage } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';
import { ApplicationFacts } from '../payment/ApplicationFacts';

const TITLE = '수강신청 상세';

export function MyApplicationPage() {
  const { applicationId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery(applicationQuery(applicationId));
  const session = useQuery(sessionQuery);
  usePageTitle(TITLE);
  const [confirming, setConfirming] = useState(false);
  const sending = useRef(false);

  const cancel = useMutation({
    mutationFn: () => cancelApplication(applicationId),
    onSuccess: async (application) => {
      queryClient.setQueryData(applicationQuery(applicationId).queryKey, application);
      await queryClient.invalidateQueries({ queryKey: ['me', 'applications', 'list'] });
      await queryClient.invalidateQueries({ queryKey: ['courses'] });
      navigate(`/me/applications/${applicationId}/cancelled`);
    },
    onSettled: () => {
      sending.current = false;
    },
  });

  const application = query.data;
  if (!application) return <QueryFallback query={query} what="신청 정보" />;

  function send() {
    if (sending.current) return;
    sending.current = true;
    cancel.mutate();
  }

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: '수강신청내역', to: '/me/applications' }, { label: TITLE }]}>
      <div className="proto">
        <ApplicationFacts application={application} applicantName={session.data?.member?.name} />
        <dl className="proto-info">
          <div>
            <dt>신청상태</dt>
            <dd>{applicationStateText(application)}</dd>
          </div>
          <div>
            <dt>환불상태</dt>
            <dd>{application.refundStage ? refundStageText(application.refundStage) : '신청 전'}</dd>
          </div>
        </dl>

        {confirming ? (
          <div className="proto-consent" role="group" aria-label="신청 취소 확인">
            <p>이 신청을 취소할까요? 취소하면 배정된 자리가 반환됩니다.</p>
            <div className="proto-actions">
              <button className="button" type="button" disabled={cancel.isPending} onClick={send}>
                취소하기
              </button>
              <button className="button secondary" type="button" onClick={() => setConfirming(false)}>
                돌아가기
              </button>
            </div>
            <FormMessage text={cancel.isError ? errorMessage(cancel.error) : ''} error />
          </div>
        ) : null}

        <div className="proto-actions">
          {application.canPay ? (
            <Link className="button" to={`/payment/${application.applicationId}`}>
              결제하기
            </Link>
          ) : null}
          {application.paymentId ? (
            <Link className="button secondary" to={`/me/receipts/${application.paymentId}`}>
              영수증
            </Link>
          ) : null}
          {application.canRequestRefund ? (
            <Link className="button secondary" to={`/me/applications/${application.applicationId}/refund`}>
              환불신청
            </Link>
          ) : null}
          {application.canCancel && !confirming ? (
            <button className="button secondary" type="button" onClick={() => setConfirming(true)}>
              신청 취소
            </button>
          ) : null}
          <Link className="button secondary" to="/me/applications">
            목록
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}