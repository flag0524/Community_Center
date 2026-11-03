// 환불 신청. 서버가 산정한 반환 기준액과 근거를 보이고 사유만 받아 접수한다. 금액은 회원이 입력하지 않는다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiRequestError } from '../../api/http';
import { createRefund } from '../../api/refunds';
import { applicationQuery, refundPreviewQuery, type RefundPreview } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { formatFee } from '../../lib/course';
import { errorMessage } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';
import { ApplicationFacts } from '../payment/ApplicationFacts';

const TITLE = '환불 신청';
const REASONS = ['수강 일정 변경', '건강상 사유', '거주지 이전', '기타'];

function basisText(basis: RefundPreview['basis']): string {
  if (basis.rule === 'BEFORE_START') return '개강 전이므로 결제한 수강료 전액을 반환합니다.';
  return `개강 후에는 당월 수강료를 제외하고 반환합니다. (교육 ${basis.educationMonths}개월 중 ${basis.elapsedMonths}개월 경과, 월 수강료 ${formatFee(basis.monthlyFee ?? 0)})`;
}

export function RefundApplyPage() {
  const { applicationId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const preview = useQuery(refundPreviewQuery(applicationId));
  const application = useQuery(applicationQuery(applicationId));
  usePageTitle(TITLE);
  const [reason, setReason] = useState(REASONS[0]!);
  const [detail, setDetail] = useState('');
  const idempotencyKey = useRef(crypto.randomUUID());
  const sending = useRef(false);

  const submit = useMutation({
    mutationFn: () => createRefund(applicationId, detail.trim() ? `${reason} · ${detail.trim()}` : reason, idempotencyKey.current),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['me'] });
      navigate('/me/refunds', { state: { created: true } });
    },
    onSettled: () => {
      sending.current = false;
    },
  });

  const crumbs = [{ label: '마이페이지' }, { label: '수강신청내역', to: '/me/applications' }, { label: TITLE }];

  if (preview.error instanceof ApiRequestError && preview.error.status === 422) {
    return (
      <ServicePage title={TITLE} crumbs={crumbs}>
        <div className="empty-state" role="status">
          <h3>{preview.error.body?.message ?? '환불을 신청할 수 없습니다.'}</h3>
          <Link className="button secondary" to={`/me/applications/${applicationId}`}>
            신청 상세
          </Link>
        </div>
      </ServicePage>
    );
  }
  if (!preview.data) return <QueryFallback query={preview} what="환불 정보" />;
  if (!application.data) return <QueryFallback query={application} what="신청 정보" />;

  const info = preview.data;
  const available = info.refundableAmount - info.reservedAmount;

  function send(event: FormEvent) {
    event.preventDefault();
    if (sending.current) return;
    sending.current = true;
    submit.mutate();
  }

  return (
    <ServicePage title={TITLE} crumbs={crumbs}>
      <div className="proto">
        <h2>환불신청 내역</h2>
        <ApplicationFacts application={application.data} />
        <dl className="proto-info">
          <div>
            <dt>결제금액</dt>
            <dd>{formatFee(info.paidAmount)}</dd>
          </div>
          <div>
            <dt>환불 가능 금액</dt>
            <dd>
              <strong>{formatFee(info.refundableAmount)}</strong>
            </dd>
          </div>
        </dl>
        <p className="proto-hint">{basisText(info.basis)}</p>
        <p className="proto-hint">환불 가능 여부와 금액·처리기간은 담당자 검토 후 안내합니다.</p>

        {available <= 0 ? (
          <div className="empty-state" role="status">
            <h3>이미 환불을 접수했습니다. 처리 결과는 환불신청 내역에서 확인해 주세요.</h3>
            <Link className="button" to="/me/refunds">
              환불신청 내역
            </Link>
          </div>
        ) : (
          <form className="proto-form" aria-label="환불 신청" noValidate onSubmit={send}>
            <label className="field">
              환불 사유
              <select value={reason} onChange={(event) => setReason(event.target.value)}>
                {REASONS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              상세 사유
              <textarea rows={4} maxLength={400} value={detail} onChange={(event) => setDetail(event.target.value)} />
            </label>
            <div className="proto-form-actions">
              <button className="button" type="submit" disabled={submit.isPending}>
                환불신청
              </button>
            </div>
            <FormMessage text={submit.isError ? errorMessage(submit.error) : ''} error />
          </form>
        )}
        <div className="proto-actions">
          <Link className="button secondary" to="/guide/refund">
            환불 안내
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}