// 강사 심사 화면. 지원 내용을 읽고 승인·반려·활동중지와 사유, 공개 여부, 검토 메모를 남긴다. 방문·외부 접수 등록도 여기서 한다 (ADM-EDU-004P)
import type { Schemas } from '@jori/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { createInstructorReview, reviewInstructor, type InstructorReviewCreate } from '../../api/review';
import { instructorReviewQuery, type InstructorReview } from '../../api/queries';
import { OwnerFiles } from '../../components/OwnerFiles';
import { Field, describe } from '../../components/Field';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { APPLICATION_SOURCE, REVIEW_STATUS } from '../../lib/labels';
import { isVersionConflict } from '../../lib/messages';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

export function InstructorReviewFormPage({ mode }: { mode: 'create' | 'review' }) {
  const { applicationId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery({ ...instructorReviewQuery(applicationId), enabled: mode === 'review' });
  if (mode === 'create') return <ReceiveForm />;
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return <ReviewForm key={data.applicationId} review={data} />;
}

type DecidedStatus = Exclude<Schemas['ReviewStatus'], 'PENDING'>;
const DECISIONS: DecidedStatus[] = ['APPROVED', 'REJECTED', 'SUSPENDED'];

function ReviewForm({ review }: { review: InstructorReview }) {
  const queryClient = useQueryClient();
  const [decision, setDecision] = useState<DecidedStatus | ''>(review.status === 'PENDING' ? '' : review.status);
  const [reason, setReason] = useState(review.reason ?? '');
  const [isPublic, setIsPublic] = useState(review.isPublic);
  const [memo, setMemo] = useState(review.memo ?? '');
  const [saved, setSaved] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      reviewInstructor(review.applicationId, { status: decision || 'PENDING', reason: reason.trim() || null, isPublic, memo: memo.trim() || null, version: review.version }),
    onSuccess: (result) => {
      queryClient.setQueryData(instructorReviewQuery(result.applicationId).queryKey, result);
      queryClient.removeQueries({ queryKey: ['reviews', 'list'] });
      setSaved(true);
    },
  });

  const server = fieldErrors(mutation.error);
  const readOnly = !review.canReview;
  const touch = () => setSaved(false);

  return (
    <>
      <div className="adm-page-heading">
        <h1>강사 심사</h1>
      </div>
      <p className="adm-state">현재 심사 상태: {REVIEW_STATUS[review.status]}</p>
      <h2 className="adm-section">지원 내용</h2>
      <dl className="adm-facts">
        <dt>지원자</dt>
        <dd>{review.applicantName}</dd>
        <dt>희망 강좌</dt>
        <dd>{review.desiredCourse}</dd>
        <dt>희망 분야</dt>
        <dd>{review.categoryName ?? '미분류'}</dd>
        <dt>접수 경로</dt>
        <dd>{APPLICATION_SOURCE[review.source]}</dd>
        <dt>접수일</dt>
        <dd>{review.receivedOn}</dd>
        <dt>경력 및 강의소개</dt>
        <dd className="adm-pre">{review.career}</dd>
      </dl>
      <h2 className="adm-section">심사</h2>
      <form
        className="adm-form"
        aria-label="강사 심사"
        noValidate
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <fieldset disabled={readOnly}>
          <div className="adm-field full">
            <span className="adm-legend" id="review-result-label">
              심사 결과
            </span>
            <div role="radiogroup" aria-labelledby="review-result-label">
              {DECISIONS.map((value) => (
                <label key={value} className="adm-radio">
                  <input
                    type="radio"
                    name="status"
                    value={value}
                    checked={decision === value}
                    onChange={() => {
                      touch();
                      setDecision(value);
                    }}
                  />
                  {REVIEW_STATUS[value]}
                </label>
              ))}
              {server.status && <p className="adm-field-error">{server.status}</p>}
            </div>
          </div>
          <div className="adm-form-grid">
            <Field id="review-reason" label="사유" error={server.reason} hint="반려·활동중지는 사유가 필수입니다." full>
              <textarea {...describe('review-reason', server.reason, '반려·활동중지는 사유가 필수입니다.')} rows={3} maxLength={500} value={reason} onChange={(event) => { touch(); setReason(event.target.value); }} />
            </Field>
            <Field id="review-public" label="공개 여부" error={server.isPublic} hint="공개 여부는 승인한 강사에게만 적용됩니다.">
              <select {...describe('review-public', server.isPublic, '공개 여부는 승인한 강사에게만 적용됩니다.')} value={isPublic ? 'Y' : 'N'} onChange={(event) => { touch(); setIsPublic(event.target.value === 'Y'); }}>
                <option value="N">비공개</option>
                <option value="Y">공개</option>
              </select>
            </Field>
            <Field id="review-memo" label="검토 메모" hint="개인정보를 입력하지 마세요." full>
              <textarea {...describe('review-memo', undefined, '개인정보를 입력하지 마세요.')} rows={3} maxLength={1000} value={memo} onChange={(event) => { touch(); setMemo(event.target.value); }} />
            </Field>
          </div>
        </fieldset>
        <p className="adm-notice">승인해도 강좌 배정이나 관리자 권한은 자동으로 부여되지 않습니다.</p>
        {saved && (
          <p className="adm-message" role="status">
            저장했습니다.
          </p>
        )}
        {mutation.isError && Object.keys(server).length === 0 && (
          <p className="adm-message error" role="alert">
            {isVersionConflict(mutation.error) ? '다른 곳에서 먼저 심사되었습니다. 목록으로 돌아가 다시 열어 주세요.' : errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          {!readOnly && (
            <button className="adm-button" type="submit" disabled={mutation.isPending}>
              저장
            </button>
          )}
          <Link className="adm-button secondary" to="/edu/instructors">
            목록
          </Link>
        </div>
      </form>
      <OwnerFiles ownerPath={`/instructor-applications/${review.applicationId}`} label="증빙" />
    </>
  );
}

function ReceiveForm() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const [values, setValues] = useState({ applicantName: '', desiredCourse: '', career: '', source: 'VISIT' as InstructorReviewCreate['source'] });
  const [missing, setMissing] = useState<Partial<Record<keyof typeof values, string>>>({});

  const mutation = useMutation({
    mutationFn: (body: InstructorReviewCreate) => createInstructorReview(body, key.current()),
    onSuccess: (result) => {
      key.renew();
      queryClient.removeQueries({ queryKey: ['reviews', 'list'] });
      void navigate(`/edu/instructors/${result.applicationId}`, { replace: true });
    },
  });

  const set = (name: keyof typeof values) => (event: { target: { value: string } }) => setValues((current) => ({ ...current, [name]: event.target.value }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Partial<Record<keyof typeof values, string>> = {};
    for (const name of ['applicantName', 'desiredCourse', 'career'] as const) if (!values[name].trim()) errors[name] = '필수 항목입니다.';
    setMissing(errors);
    if (Object.keys(errors).length === 0) mutation.mutate({ ...values, applicantName: values.applicantName.trim(), desiredCourse: values.desiredCourse.trim(), career: values.career.trim() });
  };
  const server = fieldErrors(mutation.error);
  const err = (name: keyof typeof values) => missing[name] ?? server[name];

  return (
    <>
      <div className="adm-page-heading">
        <h1>방문·외부 접수 등록</h1>
      </div>
      <p className="adm-notice">온라인 지원은 주민 화면에서 접수됩니다. 방문하거나 외부로 받은 지원서만 여기서 등록합니다.</p>
      <form className="adm-form" aria-label="지원서 등록" noValidate onSubmit={submit}>
        <div className="adm-form-grid">
          <Field id="receive-source" label="접수 경로" required error={err('source')}>
            <select {...describe('receive-source', err('source'))} value={values.source} onChange={set('source')}>
              <option value="VISIT">{APPLICATION_SOURCE.VISIT}</option>
              <option value="EXTERNAL">{APPLICATION_SOURCE.EXTERNAL}</option>
            </select>
          </Field>
          <Field id="receive-name" label="지원자" required error={err('applicantName')}>
            <input {...describe('receive-name', err('applicantName'))} value={values.applicantName} maxLength={50} onChange={set('applicantName')} />
          </Field>
          <Field id="receive-course" label="희망 강좌" required error={err('desiredCourse')} full>
            <input {...describe('receive-course', err('desiredCourse'))} value={values.desiredCourse} maxLength={100} onChange={set('desiredCourse')} />
          </Field>
          <Field id="receive-career" label="경력 및 강의소개" required error={err('career')} full>
            <textarea {...describe('receive-career', err('career'))} rows={5} maxLength={2000} value={values.career} onChange={set('career')} />
          </Field>
        </div>
        {mutation.isError && Object.keys(server).length === 0 && (
          <p className="adm-message error" role="alert">
            {errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          <button className="adm-button" type="submit" disabled={mutation.isPending}>
            등록
          </button>
          <Link className="adm-button secondary" to="/edu/instructors">
            목록
          </Link>
        </div>
      </form>
    </>
  );
}
