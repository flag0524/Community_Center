// 수강료 결제 화면. 결제수단을 고르고 남은 결제시간 안에 결제한다. 기한과 결제 가능 여부는 서버가 판정한다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { confirmPayment, openGatewayWindow, requestPayment } from '../../api/payments';
import { ApiRequestError } from '../../api/http';
import { applicationQuery, type Application, type PaymentMethod } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { formatFee } from '../../lib/course';
import { errorMessage } from '../../lib/errors';
import { formatCountdown, useCountdown } from '../../lib/countdown';
import { usePageTitle } from '../../lib/usePageTitle';
import { ApplicationFacts } from './ApplicationFacts';

const TITLE = '수강료 결제';

// 허용 결제수단은 카드와 실시간 계좌이체뿐이다(가상계좌 제외).
const METHODS: Array<{ value: PaymentMethod; label: string }> = [
  { value: 'CARD', label: '신용·체크카드' },
  { value: 'TRANSFER', label: '실시간 계좌이체' },
];

function Deadline({ application, onZero }: { application: Application; onZero: () => void }) {
  const seconds = useCountdown(application.paymentDeadline!, application.serverNow, onZero);
  return <p role="timer">남은 결제시간 {formatCountdown(seconds)}</p>;
}

export function PaymentPage() {
  const { applicationId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery(applicationQuery(applicationId));
  usePageTitle(TITLE);
  const [method, setMethod] = useState<PaymentMethod>('CARD');
  // 화면을 연 동안의 결제 시도는 같은 멱등키를 쓴다. 결과 화면에서 다시 결제하러 돌아오면 화면이 새로 만들어져 새 키를 쓴다.
  const idempotencyKey = useRef(crypto.randomUUID());
  const sending = useRef(false);

  const pay = useMutation({
    mutationFn: async (application: Application) => {
      const request = await requestPayment(application.applicationId, method, idempotencyKey.current);
      // 결제창(모의)에서 인증을 마친 뒤 승인 확인을 서버에 요청한다. 금액은 서버가 저장한 값과 대조만 한다.
      const paymentKey = await openGatewayWindow(request);
      return confirmPayment({ orderNo: request.orderNo, paymentKey, amount: request.amount });
    },
    onSettled: () => {
      sending.current = false;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: applicationQuery(applicationId).queryKey });
      navigate(`/payment/${applicationId}/result`);
    },
    onError: async (error) => {
      // 기한 만료처럼 서버가 규칙으로 거절한 경우는 신청 상태가 바뀌었으니 결과 화면이 서버 상태대로 보여 준다.
      if (error instanceof ApiRequestError && error.status === 422) {
        await queryClient.invalidateQueries({ queryKey: applicationQuery(applicationId).queryKey });
        navigate(`/payment/${applicationId}/result`);
      }
    },
  });

  const application = query.data;
  if (!application) return <QueryFallback query={query} what="신청 정보" />;

  const state = application.displayState;
  if (state !== 'PAYMENT_DUE' && state !== 'PAYMENT_FAILED') {
    const toResult = state === 'CONFIRMED' || state === 'PAYMENT_UNKNOWN' || state === 'EXPIRED';
    return <Navigate to={toResult ? `/payment/${applicationId}/result` : `/me/applications/${applicationId}`} replace />;
  }

  function send() {
    if (sending.current || !application) return;
    sending.current = true;
    pay.mutate(application);
  }

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '회원서비스' }, { label: TITLE }]}>
      <div className="proto">
        <h2>결제수단</h2>
        <fieldset className="proto-methods">
          <legend>결제수단 선택</legend>
          {METHODS.map((item) => (
            <label key={item.value} className="proto-check">
              <input
                type="radio"
                name="method"
                value={item.value}
                checked={method === item.value}
                onChange={() => setMethod(item.value)}
              />{' '}
              {item.label}
            </label>
          ))}
        </fieldset>
        <p className="proto-hint">결제 결과는 신청내역에서 확인하실 수 있습니다.</p>

        <h2>결제 내역</h2>
        <ApplicationFacts application={application} />
        <p>
          결제금액 <strong>{formatFee(application.payableAmount)}</strong>
        </p>
        <Deadline application={application} onZero={() => void query.refetch()} />

        <div className="proto-form-actions">
          <button className="button" type="button" disabled={pay.isPending} onClick={send}>
            결제하기
          </button>
        </div>
        <FormMessage text={pay.isError && !(pay.error instanceof ApiRequestError && pay.error.status === 422) ? errorMessage(pay.error) : ''} error />
        <div className="proto-actions">
          <Link className="button secondary" to={`/me/applications/${application.applicationId}`}>
            신청 상세
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}
