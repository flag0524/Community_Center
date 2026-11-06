// 감면 심사 상세 화면. 증빙 열람은 감사기록을 남기고 승인·반려는 한 번 정하면 고치지 않으며 다시 심사하려면 새 건을 만든다 (ADM-PAY-005P)
import type { Schemas } from '@jori/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { decideReduction, reReviewReduction, viewEvidence, type ReductionReview } from '../../api/reductions';
import { reductionQuery } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { Field, describe } from '../../components/Field';
import { TableWrap } from '../../components/ListParts';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { FILE_STATUS, REDUCTION_STATUS, REDUCTION_TYPE } from '../../lib/labels';
import { allFieldMessages, isVersionConflict } from '../../lib/messages';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

export function ReductionDetailPage() {
  const { reviewId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(reductionQuery(reviewId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return <ReductionDetail key={`${data.reviewId}-${data.version}`} review={data} />;
}

function ReductionDetail({ review }: { review: ReductionReview }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const [decision, setDecision] = useState<Schemas['ReductionDecision']>('APPROVE');
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const [validUntil, setValidUntil] = useState('');
  const [missing, setMissing] = useState<Record<string, string>>({});
  const [confirming, setConfirming] = useState(false);

  const refresh = (result: ReductionReview) => {
    queryClient.setQueryData(reductionQuery(result.reviewId).queryKey, result);
    void queryClient.invalidateQueries({ queryKey: ['reductions', 'list'] });
  };
  const view = useMutation({ mutationFn: (fileId: string) => viewEvidence(review.reviewId, fileId), onSuccess: refresh });
  const decide = useMutation({
    mutationFn: () => decideReduction(review.reviewId, { decision, reviewNote: note.trim() || null, rejectReason: decision === 'REJECT' ? reason.trim() : null, validUntil: decision === 'APPROVE' ? validUntil : null, version: review.version }),
    onSuccess: refresh,
    onSettled: () => setConfirming(false),
  });
  const reReview = useMutation({
    mutationFn: () => reReviewReduction(review.reviewId, key.current()),
    onSuccess: (result) => {
      key.renew();
      void queryClient.invalidateQueries({ queryKey: ['reductions', 'list'] });
      void navigate(`/pay/reductions/${result.reviewId}`);
    },
  });

  const check = () => {
    const errors: Record<string, string> = {};
    if (decision === 'APPROVE' && !validUntil) errors.validUntil = '승인 유효 종료일을 입력해 주세요.';
    if (decision === 'REJECT' && !reason.trim()) errors.rejectReason = '반려 사유를 입력해 주세요.';
    setMissing(errors);
    setConfirming(Object.keys(errors).length === 0);
  };
  const server = fieldErrors(decide.error);
  const err = (name: string) => missing[name] ?? server[name];
  const failure = [view, decide, reReview].find((mutation) => mutation.isError && Object.keys(fieldErrors(mutation.error)).length === 0)?.error;
  const viewFailure = view.isError ? allFieldMessages(view.error) : '';

  return (
    <>
      <div className="adm-page-heading">
        <h1>감면 심사 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>회원</dt>
        <dd>{review.memberName}</dd>
        <dt>기수</dt>
        <dd>{review.cycleName}</dd>
        <dt>감면 유형</dt>
        <dd>{REDUCTION_TYPE[review.reductionType]}</dd>
        <dt>조리읍 거주 확인</dt>
        <dd>{review.residenceConfirmed ? '확인됨' : '확인 안 됨'}</dd>
        <dt>신청일</dt>
        <dd>{review.appliedOn}</dd>
        <dt>상태</dt>
        <dd>{REDUCTION_STATUS[review.status]}</dd>
        {review.reviewedBy && (
          <>
            <dt>심사</dt>
            <dd>
              {review.reviewedBy} · {review.reviewedAt ? kstDateTime(review.reviewedAt) : ''}
            </dd>
          </>
        )}
        {review.validUntil && (
          <>
            <dt>승인 유효 종료일</dt>
            <dd>{review.validUntil}</dd>
          </>
        )}
        {review.rejectReason && (
          <>
            <dt>반려 사유</dt>
            <dd className="adm-pre">{review.rejectReason}</dd>
          </>
        )}
        {review.reviewNote && (
          <>
            <dt>심사 내용</dt>
            <dd className="adm-pre">{review.reviewNote}</dd>
          </>
        )}
      </dl>

      <h2 className="adm-section">증빙</h2>
      {review.evidence.length > 0 ? (
        <TableWrap label="증빙 목록">
          <table>
            <thead>
              <tr>
                <th scope="col">파일명</th>
                <th scope="col">검사상태</th>
                <th scope="col">열람</th>
              </tr>
            </thead>
            <tbody>
              {review.evidence.map((file) => (
                <tr key={file.fileId}>
                  <td>{file.fileName}</td>
                  <td>{FILE_STATUS[file.status]}</td>
                  <td>
                    {review.canViewEvidence ? (
                      <button type="button" className="adm-button secondary" aria-label={`열람 (${file.fileName})`} disabled={view.isPending} onClick={() => view.mutate(file.fileId)}>
                        열람
                      </button>
                    ) : (
                      '-'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>제출된 증빙이 없습니다.</p>
      )}
      {viewFailure && (
        <p className="adm-message error" role="alert">
          {viewFailure}
        </p>
      )}
      <p className="adm-notice">증빙은 비공개이고 열람할 때마다 열람자와 시각이 기록됩니다. 파일 보기는 첨부 기능이 생기면 더합니다.</p>

      <h2 className="adm-section">열람 기록</h2>
      {review.evidenceViews.length > 0 ? (
        <TableWrap label="열람 기록">
          <table>
            <thead>
              <tr>
                <th scope="col">시각</th>
                <th scope="col">담당자</th>
                <th scope="col">파일</th>
              </tr>
            </thead>
            <tbody>
              {review.evidenceViews.map((entry) => (
                <tr key={`${entry.at}-${entry.fileName}`}>
                  <td>{kstDateTime(entry.at)}</td>
                  <td>{entry.by}</td>
                  <td>{entry.fileName}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>열람 기록이 없습니다.</p>
      )}

      {review.canDecide && (
        <>
          <h2 className="adm-section">심사</h2>
          <form className="adm-form" aria-label="감면 심사" noValidate onSubmit={(event) => event.preventDefault()}>
            <fieldset>
              <legend className="adm-legend">결정</legend>
              {(['APPROVE', 'REJECT'] as const).map((value) => (
                <label key={value} className="adm-radio">
                  <input type="radio" name="decision" checked={decision === value} onChange={() => { setDecision(value); setConfirming(false); setMissing({}); }} />
                  {value === 'APPROVE' ? '승인' : '반려'}
                </label>
              ))}
              {server.decision && <p className="adm-field-error">{server.decision}</p>}
            </fieldset>
            <div className="adm-form-grid">
              {decision === 'APPROVE' ? (
                <Field id="red-until" label="승인 유효 종료일" required error={err('validUntil')}>
                  <input {...describe('red-until', err('validUntil'))} type="date" value={validUntil} onChange={(event) => { setValidUntil(event.target.value); setConfirming(false); }} />
                </Field>
              ) : (
                <Field id="red-reason" label="반려 사유" required error={err('rejectReason')} full>
                  <textarea {...describe('red-reason', err('rejectReason'))} rows={3} maxLength={4000} value={reason} onChange={(event) => { setReason(event.target.value); setConfirming(false); }} />
                </Field>
              )}
              <Field id="red-note" label="심사 내용" full>
                <textarea {...describe('red-note')} rows={3} maxLength={4000} value={note} onChange={(event) => setNote(event.target.value)} />
              </Field>
            </div>
            <p className="adm-notice">결정한 뒤에는 내용과 증빙을 고칠 수 없습니다. 다시 심사하려면 새 심사건을 만듭니다.</p>
            <div className="adm-actions">
              {confirming ? (
                <>
                  <button type="button" className="adm-button danger" disabled={decide.isPending} onClick={() => decide.mutate()}>
                    {decision === 'APPROVE' ? '정말 승인' : '정말 반려'}
                  </button>
                  <button type="button" className="adm-button secondary" onClick={() => setConfirming(false)}>
                    취소
                  </button>
                </>
              ) : (
                <button type="button" className="adm-button" onClick={check}>
                  결정
                </button>
              )}
            </div>
          </form>
        </>
      )}

      {failure !== undefined && (
        <p className="adm-message error" role="alert">
          {isVersionConflict(failure) ? '다른 곳에서 먼저 바뀌었습니다. 목록에서 다시 열어 주세요.' : errorMessage(failure)}
        </p>
      )}
      <div className="adm-actions">
        {review.canReReview && <ConfirmButton label="재심사" confirmLabel="정말 재심사" target={review.memberName} disabled={reReview.isPending} onConfirm={() => reReview.mutate()} />}
        <Link className="adm-button secondary" to="/pay/reductions">
          목록
        </Link>
      </div>
    </>
  );
}