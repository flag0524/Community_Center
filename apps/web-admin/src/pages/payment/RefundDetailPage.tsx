// 환불 검토 상세 화면. 한도·기준액을 보며 승인·반려·보류를 정하고(AU.RFND_A), 승인된 건은 다른 담당자가 집행한다(AU.RFND_X) (ADM-PAY-004P)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { approveRefund, confirmRefundDone, executeRefund, holdRefund, rejectRefund, releaseRefundHold, type AdminRefund } from '../../api/refunds';
import { adminRefundQuery } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { Field, describe } from '../../components/Field';
import { TableWrap } from '../../components/ListParts';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { kstDateTime, won } from '../../lib/format';
import { EXECUTION_METHOD, PAYMENT_METHOD, REFUND_REQUESTER, REFUND_RULE, REFUND_STATUS } from '../../lib/labels';
import { allFieldMessages, isVersionConflict } from '../../lib/messages';

export function RefundDetailPage() {
  const { refundId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(adminRefundQuery(refundId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return <RefundDetail key={data.refundId} refund={data} />;
}

function RefundDetail({ refund }: { refund: AdminRefund }) {
  const queryClient = useQueryClient();
  const refresh = (result: AdminRefund) => {
    queryClient.setQueryData(adminRefundQuery(result.refundId).queryKey, result);
    queryClient.removeQueries({ queryKey: ['refunds', 'list'] });
  };
  const release = useMutation({ mutationFn: () => releaseRefundHold(refund.refundId, refund.version), onSuccess: refresh });
  const execute = useMutation({ mutationFn: () => executeRefund(refund.refundId, refund.version), onSuccess: refresh });
  const confirmDone = useMutation({ mutationFn: () => confirmRefundDone(refund.refundId, refund.version), onSuccess: refresh });
  const actionError = release.error ?? execute.error ?? confirmDone.error;
  const afterApproval = ['APPROVED', 'PENDING', 'FAILED', 'DONE'].includes(refund.status);

  return (
    <>
      <div className="adm-page-heading">
        <h1>환불 검토 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>환불번호</dt>
        <dd>{refund.refundNo}</dd>
        <dt>상태</dt>
        <dd>
          {REFUND_STATUS[refund.status]} · 경과 {refund.elapsedBusinessDays}영업일
          {refund.overdue && <strong className="adm-overdue"> · 3영업일 초과</strong>}
        </dd>
        <dt>원결제</dt>
        <dd>
          {refund.paymentOrderNo} · {won(refund.paidAmount)} · {PAYMENT_METHOD[refund.paymentMethod]} · 승인 {kstDateTime(refund.paidAt)}
        </dd>
        <dt>한도</dt>
        <dd>
          기환불·예약 {won(refund.reservedAmount)} / 남은 환불 가능 {won(refund.remainingAmount)}
        </dd>
        <dt>기준액</dt>
        <dd>
          {won(refund.baselineAmount)} ({REFUND_RULE[refund.baselineRule]}) · 교육 시작 {refund.educationStart}
        </dd>
        <dt>요청</dt>
        <dd>
          {won(refund.requestedAmount)} · 사유 {refund.reason}
          {refund.detail && ` · ${refund.detail}`} · 증빙 {refund.evidenceCount}건
        </dd>
        <dt>요청 주체</dt>
        <dd>
          {REFUND_REQUESTER[refund.requester]} · {refund.requesterName} · 접수 {refund.receivedOn}
        </dd>
        {refund.decidedBy && (
          <>
            <dt>결정</dt>
            <dd>
              {refund.decidedBy}
              {refund.approvedAmount !== null && ` · 승인액 ${won(refund.approvedAmount)}`}
              {refund.decisionReason && ` · ${refund.decisionReason}`}
            </dd>
          </>
        )}
      </dl>

      {refund.canReview && (
        <>
          <h2 className="adm-section">검토</h2>
          {refund.status === 'ON_HOLD' ? (
            <div className="adm-actions">
              <p>보류 사유: {refund.decisionReason}</p>
              <button className="adm-button secondary" type="button" disabled={release.isPending} onClick={() => release.mutate()}>
                보류 해제
              </button>
            </div>
          ) : (
            <ReviewForm refund={refund} onDone={refresh} />
          )}
        </>
      )}

      {afterApproval && (
        <>
          <h2 className="adm-section">집행</h2>
          <dl className="adm-facts">
            <dt>방법</dt>
            <dd>{EXECUTION_METHOD[refund.executionMethod]}</dd>
            <dt>결과</dt>
            <dd>{refund.executionResult ?? '-'}</dd>
            {refund.executedBy && (
              <>
                <dt>집행 담당</dt>
                <dd>{refund.executedBy}</dd>
              </>
            )}
            {refund.manualAccount && (
              <>
                <dt>계좌</dt>
                <dd>
                  {refund.manualAccount.bankName} · {refund.manualAccount.holderMasked} · {refund.manualAccount.accountMasked}
                </dd>
              </>
            )}
          </dl>
          <div className="adm-actions">
            {refund.canExecute && (
              <ConfirmButton
                label={refund.status === 'FAILED' ? '재처리' : '집행 요청'}
                confirmLabel={refund.status === 'FAILED' ? '정말 재처리' : '정말 집행 요청'}
                target={refund.refundNo}
                disabled={execute.isPending}
                onConfirm={() => execute.mutate()}
              />
            )}
            {refund.canConfirmTransfer && (
              <ConfirmButton label="이체 완료 확인" confirmLabel="정말 이체 완료 확인" target={refund.refundNo} disabled={confirmDone.isPending} onConfirm={() => confirmDone.mutate()} />
            )}
          </div>
          {refund.executeNote && <p className="adm-notice">{refund.executeNote}</p>}
        </>
      )}
      {actionError && (
        <p className="adm-message error" role="alert">
          {isVersionConflict(actionError) ? '다른 곳에서 먼저 처리되었습니다. 화면을 새로 열어 주세요.' : allFieldMessages(actionError) || errorMessage(actionError)}
        </p>
      )}

      <h2 className="adm-section">이력</h2>
      <TableWrap label="환불 이력">
        <table>
          <thead>
            <tr>
              <th scope="col">시각</th>
              <th scope="col">상태</th>
              <th scope="col">처리자</th>
              <th scope="col">비고</th>
            </tr>
          </thead>
          <tbody>
            {refund.history.map((entry) => (
              <tr key={`${entry.at}-${entry.status}`}>
                <td>{kstDateTime(entry.at)}</td>
                <td>{REFUND_STATUS[entry.status]}</td>
                <td>{entry.actor}</td>
                <td>{entry.note ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
      <div className="adm-actions">
        <Link className="adm-button secondary" to="/pay/refunds">
          목록
        </Link>
      </div>
    </>
  );
}

type Decision = 'APPROVE' | 'REJECT' | 'HOLD';
const DECISIONS: Array<[Decision, string]> = [
  ['APPROVE', '승인'],
  ['REJECT', '반려'],
  ['HOLD', '보류'],
];

function ReviewForm({ refund, onDone }: { refund: AdminRefund; onDone: (result: AdminRefund) => void }) {
  const [decision, setDecision] = useState<Decision | ''>('');
  const [amount, setAmount] = useState(String(Math.min(refund.requestedAmount, refund.remainingAmount)));
  const [reason, setReason] = useState('');
  const [missing, setMissing] = useState<Record<string, string>>({});
  const [confirming, setConfirming] = useState(false);

  const mutation = useMutation({
    mutationFn: () => {
      if (decision === 'APPROVE') return approveRefund(refund.refundId, Number(amount), refund.version);
      if (decision === 'REJECT') return rejectRefund(refund.refundId, reason.trim(), refund.version);
      return holdRefund(refund.refundId, reason.trim(), refund.version);
    },
    onSuccess: onDone,
    onError: () => setConfirming(false),
  });

  const server = fieldErrors(mutation.error);
  const err = (name: string) => missing[name] ?? server[name];
  const reset = () => setConfirming(false);

  const check = () => {
    const errors: Record<string, string> = {};
    if (!decision) errors.decision = '결정을 선택해 주세요.';
    if (decision === 'APPROVE' && !(Number(amount) >= 1)) errors.amount = '1원 이상의 승인액을 입력해 주세요.';
    if ((decision === 'REJECT' || decision === 'HOLD') && !reason.trim()) errors.reason = '반려·보류는 사유가 필수입니다.';
    setMissing(errors);
    if (Object.keys(errors).length === 0) setConfirming(true);
  };

  return (
    <form className="adm-form" aria-label="환불 결정" noValidate onSubmit={(event) => event.preventDefault()}>
      <div className="adm-field full">
        <span className="adm-legend" id="refund-decision-label">
          결정
        </span>
        <div role="radiogroup" aria-labelledby="refund-decision-label">
          {DECISIONS.map(([value, label]) => (
            <label key={value} className="adm-radio">
              <input type="radio" name="decision" value={value} checked={decision === value} onChange={() => { reset(); setDecision(value); }} />
              {label}
            </label>
          ))}
          {err('decision') && <p className="adm-field-error">{err('decision')}</p>}
        </div>
      </div>
      <div className="adm-form-grid">
        {decision === 'APPROVE' && (
          <Field id="refund-approve-amount" label="승인액(원)" required error={err('amount')} hint="승인액과 기존 예약액의 합이 원결제액을 넘을 수 없습니다.">
            <input
              {...describe('refund-approve-amount', err('amount'), '승인액과 기존 예약액의 합이 원결제액을 넘을 수 없습니다.')}
              type="number"
              min={1}
              value={amount}
              onChange={(event) => { reset(); setAmount(event.target.value); }}
            />
          </Field>
        )}
        <Field id="refund-reason" label="사유" required={decision === 'REJECT' || decision === 'HOLD'} error={err('reason')} hint="반려·보류는 사유가 필수입니다." full>
          <textarea
            {...describe('refund-reason', err('reason'), '반려·보류는 사유가 필수입니다.')}
            rows={3}
            maxLength={500}
            value={reason}
            onChange={(event) => { reset(); setReason(event.target.value); }}
          />
        </Field>
      </div>
      {mutation.isError && Object.keys(server).length === 0 && (
        <p className="adm-message error" role="alert">
          {isVersionConflict(mutation.error) ? '다른 곳에서 먼저 처리되었습니다. 화면을 새로 열어 주세요.' : errorMessage(mutation.error)}
        </p>
      )}
      {confirming ? (
        <div className="adm-notice" role="group" aria-label="결정 확정 확인">
          <p>
            <strong>{DECISIONS.find(([value]) => value === decision)?.[1]}</strong>으로 결정합니다.
            {decision === 'APPROVE' && ' 승인하면 승인액만큼 환불 한도가 예약됩니다.'}
          </p>
          <div className="adm-actions">
            <button className="adm-button danger" type="button" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
              확정
            </button>
            <button className="adm-button secondary" type="button" onClick={reset}>
              취소
            </button>
          </div>
        </div>
      ) : (
        <div className="adm-actions">
          <button className="adm-button" type="button" onClick={check}>
            결정 저장
          </button>
        </div>
      )}
    </form>
  );
}
