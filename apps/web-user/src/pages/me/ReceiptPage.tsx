// 결제 영수증. 결제 내역과 승인번호를 보이고 인쇄할 수 있다
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { receiptQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { PAYMENT_METHOD_LABEL } from '../../lib/applicationLabels';
import { formatFee } from '../../lib/course';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '결제 영수증';

export function ReceiptPage() {
  const { paymentId = '' } = useParams();
  const query = useQuery(receiptQuery(paymentId));
  usePageTitle(TITLE);
  const receipt = query.data;

  if (!receipt) return <QueryFallback query={query} what="영수증" />;

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: TITLE }]}>
      <div className="proto">
        <h2>수강료 결제 내역</h2>
        <dl className="proto-info">
          <div>
            <dt>강좌명</dt>
            <dd>{receipt.courseName}</dd>
          </div>
          <div>
            <dt>수강료</dt>
            <dd>{formatFee(receipt.amount)}</dd>
          </div>
          <div>
            <dt>신청번호</dt>
            <dd>{receipt.applicationId}</dd>
          </div>
          <div>
            <dt>신청자</dt>
            <dd>{receipt.payerName}</dd>
          </div>
          <div>
            <dt>승인번호</dt>
            <dd>{receipt.approvalNo}</dd>
          </div>
          <div>
            <dt>결제수단</dt>
            <dd>{PAYMENT_METHOD_LABEL[receipt.method]}</dd>
          </div>
        </dl>
        <div className="proto-actions">
          <button className="button" type="button" onClick={() => window.print()}>
            인쇄
          </button>
          <Link className="button secondary" to={`/me/applications/${receipt.applicationId}`}>
            신청 상세
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}