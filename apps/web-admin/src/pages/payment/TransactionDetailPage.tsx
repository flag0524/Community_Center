// 결제·거래 상세 화면. PG 통보 이력과 조치 이력을 보고, 결과 확인 중인 거래는 PG 재조회와 수동 대사를 한다 (ADM-PAY-003P)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { reconcileTransaction, recheckTransaction } from '../../api/transactions';
import { transactionQuery, type Transaction } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { TableWrap } from '../../components/ListParts';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { kstDateTime, won } from '../../lib/format';
import { ACTION_KIND, NOTICE_HANDLING, PAYMENT_METHOD, PAYMENT_STATUS, RECONCILE_OUTCOME, REFUND_STATUS, DISPLAY_STATE } from '../../lib/labels';
import { isVersionConflict } from '../../lib/messages';

export function TransactionDetailPage() {
  const { transactionId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(transactionQuery(transactionId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return <TransactionDetail key={data.transactionId} transaction={data} />;
}

function TransactionDetail({ transaction }: { transaction: Transaction }) {
  const queryClient = useQueryClient();
  const refresh = (result: Transaction) => {
    queryClient.setQueryData(transactionQuery(result.transactionId).queryKey, result);
    queryClient.removeQueries({ queryKey: ['transactions', 'list'] });
  };
  const recheck = useMutation({ mutationFn: () => recheckTransaction(transaction.transactionId), onSuccess: refresh });

  return (
    <>
      <div className="adm-page-heading">
        <h1>결제·거래 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>주문번호</dt>
        <dd>{transaction.orderNo}</dd>
        <dt>상태</dt>
        <dd>
          {PAYMENT_STATUS[transaction.status]}
          {transaction.status === 'PENDING' && ` · 재조회 ${transaction.recheckCount}/${transaction.recheckMax}`}
          {transaction.lastRecheckAt && ` (마지막 ${kstDateTime(transaction.lastRecheckAt).slice(11)})`}
        </dd>
        <dt>신청</dt>
        <dd>
          {transaction.applicationNo} · {transaction.courseName} · {transaction.applicantName} · {DISPLAY_STATE[transaction.applicationState]}
        </dd>
        <dt>금액</dt>
        <dd>
          {won(transaction.amount)} · {PAYMENT_METHOD[transaction.method]} · 가맹점 {transaction.merchantId}
        </dd>
        <dt>승인 요청</dt>
        <dd>{kstDateTime(transaction.requestedAt)}</dd>
        <dt>PG 승인</dt>
        <dd>{transaction.approvedAt ? kstDateTime(transaction.approvedAt) : '-'}</dd>
        <dt>결제기한</dt>
        <dd>{transaction.paymentDeadlineAt ? kstDateTime(transaction.paymentDeadlineAt) : '-'}</dd>
      </dl>

      <h2 className="adm-section">PG 통보 이력</h2>
      {transaction.notices.length > 0 ? (
        <TableWrap label="PG 통보 이력">
          <table>
            <thead>
              <tr>
                <th scope="col">시각</th>
                <th scope="col">내용 해시</th>
                <th scope="col">처리</th>
              </tr>
            </thead>
            <tbody>
              {transaction.notices.map((notice) => (
                <tr key={`${notice.at}-${notice.hashPrefix}`}>
                  <td>{kstDateTime(notice.at)}</td>
                  <td>{notice.hashPrefix}…</td>
                  <td>{NOTICE_HANDLING[notice.handling]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>받은 PG 통보가 없습니다.</p>
      )}

      <h2 className="adm-section">조치 이력</h2>
      {transaction.actions.length > 0 ? (
        <TableWrap label="조치 이력">
          <table>
            <thead>
              <tr>
                <th scope="col">시각</th>
                <th scope="col">조치</th>
                <th scope="col">처리자</th>
                <th scope="col">결과</th>
              </tr>
            </thead>
            <tbody>
              {transaction.actions.map((action) => (
                <tr key={`${action.at}-${action.kind}`}>
                  <td>{kstDateTime(action.at)}</td>
                  <td>{ACTION_KIND[action.kind]}</td>
                  <td>{action.actor}</td>
                  <td>{action.result}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>조치 이력이 없습니다.</p>
      )}

      {(transaction.canRecheck || transaction.canReconcile) && (
        <>
          <h2 className="adm-section">조치</h2>
          <p className="adm-notice">확인되지 않은 상태를 임의로 실패·취소 처리하지 마세요. PG 관리자 화면에서 확인한 결과만 입력합니다.</p>
          {transaction.canRecheck && (
            <div className="adm-actions">
              <button className="adm-button secondary" type="button" disabled={recheck.isPending} onClick={() => recheck.mutate()}>
                PG 재조회
              </button>
            </div>
          )}
          {recheck.isError && (
            <p className="adm-message error" role="alert">
              {errorMessage(recheck.error)}
            </p>
          )}
          {transaction.canReconcile && <ReconcileForm transaction={transaction} onDone={refresh} />}
        </>
      )}

      <h2 className="adm-section">연결 환불</h2>
      {transaction.refund ? (
        <p>
          {transaction.refund.refundNo} · {won(transaction.refund.amount)} · {REFUND_STATUS[transaction.refund.status]}
        </p>
      ) : (
        <p>연결된 환불이 없습니다.</p>
      )}
      <div className="adm-actions">
        <Link className="adm-button secondary" to="/pay/transactions">
          목록
        </Link>
      </div>
    </>
  );
}

function ReconcileForm({ transaction, onDone }: { transaction: Transaction; onDone: (result: Transaction) => void }) {
  const [outcome, setOutcome] = useState<'PAID' | 'FAILED' | ''>('');
  const [approvalNo, setApprovalNo] = useState('');
  const [evidence, setEvidence] = useState('');
  const [missing, setMissing] = useState<Record<string, string>>({});
  const [confirming, setConfirming] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      reconcileTransaction(transaction.transactionId, {
        outcome: outcome as 'PAID' | 'FAILED',
        approvalNo: outcome === 'PAID' ? approvalNo.trim() : null,
        evidence: evidence.trim(),
        version: transaction.version,
      }),
    onSuccess: onDone,
    onError: () => setConfirming(false),
  });

  const server = fieldErrors(mutation.error);
  const err = (name: string) => missing[name] ?? server[name];

  const check = () => {
    const errors: Record<string, string> = {};
    if (!outcome) errors.outcome = '대사 결과를 선택해 주세요.';
    if (outcome === 'PAID' && !approvalNo.trim()) errors.approvalNo = '성공으로 처리하려면 PG 승인번호가 필요합니다.';
    if (!evidence.trim()) errors.evidence = '확인 근거는 필수입니다.';
    setMissing(errors);
    if (Object.keys(errors).length === 0) setConfirming(true);
  };

  return (
    <form className="adm-form" aria-label="수동 대사" noValidate onSubmit={(event) => event.preventDefault()}>
      <div className="adm-field full">
        <span className="adm-legend" id="reconcile-outcome-label">
          대사 결과
        </span>
        <div role="radiogroup" aria-labelledby="reconcile-outcome-label">
          {(['PAID', 'FAILED'] as const).map((value) => (
            <label key={value} className="adm-radio">
              <input type="radio" name="outcome" value={value} checked={outcome === value} onChange={() => { setConfirming(false); setOutcome(value); }} />
              {RECONCILE_OUTCOME[value]}
            </label>
          ))}
          {err('outcome') && <p className="adm-field-error">{err('outcome')}</p>}
        </div>
      </div>
      <div className="adm-form-grid">
        {outcome === 'PAID' && (
          <Field id="reconcile-approval" label="PG 승인번호" required error={err('approvalNo')}>
            <input {...describe('reconcile-approval', err('approvalNo'))} value={approvalNo} maxLength={40} onChange={(event) => { setConfirming(false); setApprovalNo(event.target.value); }} />
          </Field>
        )}
        <Field
          id="reconcile-evidence"
          label="확인 근거"
          required
          error={err('evidence')}
          full
          hint="PG 관리자 화면에서 확인한 내용을 적어 주세요. 캡처 파일 첨부는 첨부 기능이 생기면 더합니다."
        >
          <textarea
            {...describe('reconcile-evidence', err('evidence'), 'PG 관리자 화면에서 확인한 내용을 적어 주세요. 캡처 파일 첨부는 첨부 기능이 생기면 더합니다.')}
            rows={3}
            maxLength={1000}
            value={evidence}
            onChange={(event) => { setConfirming(false); setEvidence(event.target.value); }}
          />
        </Field>
      </div>
      {mutation.isError && Object.keys(server).length === 0 && (
        <p className="adm-message error" role="alert">
          {isVersionConflict(mutation.error) ? '다른 곳에서 먼저 처리되었습니다. 화면을 새로 열어 주세요.' : errorMessage(mutation.error)}
        </p>
      )}
      {confirming ? (
        <div className="adm-notice" role="group" aria-label="대사 확정 확인">
          <p>
            입력한 내용으로 <strong>{outcome ? RECONCILE_OUTCOME[outcome] : ''}</strong> 처리를 확정합니다. 확정하면 되돌릴 수 없습니다.
          </p>
          <div className="adm-actions">
            <button className="adm-button danger" type="button" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
              확정
            </button>
            <button className="adm-button secondary" type="button" onClick={() => setConfirming(false)}>
              취소
            </button>
          </div>
        </div>
      ) : (
        <div className="adm-actions">
          <button className="adm-button" type="button" onClick={check}>
            대사 결과 저장
          </button>
        </div>
      )}
    </form>
  );
}
