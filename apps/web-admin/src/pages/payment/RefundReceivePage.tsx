// 방문·유선 환불 접수 화면. 담당자가 결제완료 신청에 대해 환불 요청을 대신 접수한다. 승인은 상세에서 따로 한다 (ADM-PAY-004)
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createAdminRefund } from '../../api/refunds';
import { Field, describe } from '../../components/Field';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

export function RefundReceivePage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const [values, setValues] = useState({ applicationNo: '', requestedAmount: '', reason: '', detail: '' });
  const [missing, setMissing] = useState<Record<string, string>>({});

  const mutation = useMutation({
    mutationFn: () =>
      createAdminRefund(
        { applicationNo: values.applicationNo.trim(), requestedAmount: Number(values.requestedAmount), reason: values.reason.trim(), detail: values.detail.trim() || null },
        key.current(),
      ),
    onSuccess: (result) => {
      key.renew();
      queryClient.removeQueries({ queryKey: ['refunds', 'list'] });
      void navigate(`/pay/refunds/${result.refundId}`, { replace: true });
    },
  });

  const set = (name: keyof typeof values) => (event: { target: { value: string } }) => setValues((current) => ({ ...current, [name]: event.target.value }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!values.applicationNo.trim()) errors.applicationNo = '필수 항목입니다.';
    if (!(Number(values.requestedAmount) >= 1)) errors.requestedAmount = '1원 이상의 금액을 입력해 주세요.';
    if (!values.reason.trim()) errors.reason = '필수 항목입니다.';
    setMissing(errors);
    if (Object.keys(errors).length === 0) mutation.mutate();
  };
  const server = fieldErrors(mutation.error);
  const err = (name: string) => missing[name] ?? server[name];

  return (
    <>
      <div className="adm-page-heading">
        <h1>방문·유선 환불 접수</h1>
      </div>
      <p className="adm-notice">결제가 완료된 신청만 접수할 수 있습니다. 접수한 환불은 심사 상세에서 승인·반려·보류를 따로 정합니다.</p>
      <form className="adm-form" aria-label="환불 접수" noValidate onSubmit={submit}>
        <div className="adm-form-grid">
          <Field id="refund-application" label="신청번호" required error={err('applicationNo')}>
            <input {...describe('refund-application', err('applicationNo'))} value={values.applicationNo} maxLength={30} onChange={set('applicationNo')} />
          </Field>
          <Field id="refund-amount" label="요청액(원)" required error={err('requestedAmount')}>
            <input {...describe('refund-amount', err('requestedAmount'))} type="number" min={1} value={values.requestedAmount} onChange={set('requestedAmount')} />
          </Field>
          <Field id="refund-reason" label="환불 사유" required error={err('reason')} full>
            <input {...describe('refund-reason', err('reason'))} value={values.reason} maxLength={500} onChange={set('reason')} />
          </Field>
          <Field id="refund-detail" label="상세 내용" full>
            <textarea {...describe('refund-detail')} rows={4} maxLength={2000} value={values.detail} onChange={set('detail')} />
          </Field>
        </div>
        {mutation.isError && Object.keys(server).length === 0 && (
          <p className="adm-message error" role="alert">
            {errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          <button className="adm-button" type="submit" disabled={mutation.isPending}>
            접수
          </button>
          <Link className="adm-button secondary" to="/pay/refunds">
            목록
          </Link>
        </div>
      </form>
    </>
  );
}
