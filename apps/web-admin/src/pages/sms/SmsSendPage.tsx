// 문자 발송 화면. 대상을 고르고 미리보기로 수신자 수를 확인한 뒤 최종 확인 체크를 해야만 발송을 요청한다 (ADM-SYS-001P)
import type { Schemas } from '@jori/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { previewSms, sendSms, type SmsAudience, type SmsPreview } from '../../api/sms';
import { courseOptionsQuery } from '../../api/queries';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { SMS_AUDIENCE } from '../../lib/labels';
import { isStateConflict } from '../../lib/messages';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

const MAX_BYTES = 90;
const STATUSES = Object.keys(SMS_AUDIENCE) as Array<Schemas['SmsAudienceStatus']>;
// 화면의 글자 수 안내용이다. 허용 여부는 서버가 정한다.
const byteLength = (text: string) => [...text].reduce((sum, char) => sum + (char.codePointAt(0)! > 127 ? 2 : 1), 0);

export function SmsSendPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const options = useQuery(courseOptionsQuery);
  const [scope, setScope] = useState<'CENTER' | 'COURSE'>('CENTER');
  const [courseIds, setCourseIds] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<Array<Schemas['SmsAudienceStatus']>>(['CONFIRMED', 'PAYMENT_PENDING']);
  const [content, setContent] = useState('');
  const [preview, setPreview] = useState<SmsPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [stale, setStale] = useState(false);
  const [missing, setMissing] = useState<Record<string, string>>({});

  const audience = (): SmsAudience => ({ scope, courseIds: scope === 'COURSE' ? courseIds : [], statuses, content });
  const changed = () => {
    setPreview(null);
    setConfirmed(false);
    setStale(false);
  };

  const previewMutation = useMutation({ mutationFn: () => previewSms(audience()), onSuccess: setPreview });
  const sendMutation = useMutation({
    mutationFn: () => sendSms({ ...audience(), confirmed: true, expectedRecipientCount: preview?.recipientCount ?? 0 }, key.current()),
    onSuccess: (result) => {
      key.renew();
      void queryClient.invalidateQueries({ queryKey: ['sms', 'list'] });
      void navigate(`/sys/sms/${result.smsId}`, { replace: true, state: { sent: true } });
    },
    onError: (error) => {
      // 미리보기 뒤에 대상이 바뀌었다. 서버가 다시 산정한 수를 보이고 다시 확인받는다.
      if (isStateConflict(error)) {
        setConfirmed(false);
        setStale(true);
        previewMutation.mutate();
      }
    },
  });

  const runPreview = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (scope === 'COURSE' && courseIds.length === 0) errors.courseIds = '강좌를 하나 이상 선택해 주세요.';
    if (statuses.length === 0) errors.statuses = '대상 상태를 하나 이상 선택해 주세요.';
    if (!content.trim()) errors.content = '문안을 입력해 주세요.';
    setMissing(errors);
    setConfirmed(false);
    setStale(false);
    if (Object.keys(errors).length === 0) previewMutation.mutate();
  };

  const server = fieldErrors(previewMutation.error);
  const err = (name: string) => missing[name] ?? server[name];
  const bytes = byteLength(content);
  const toggle = <T,>(list: T[], value: T): T[] => (list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);

  return (
    <>
      <div className="adm-page-heading">
        <h1>문자 발송</h1>
      </div>
      <form className="adm-form" aria-label="문자 발송" noValidate onSubmit={runPreview}>
        <fieldset>
          <legend className="adm-legend">수신 범위</legend>
          <label className="adm-radio">
            <input type="radio" name="scope" checked={scope === 'CENTER'} onChange={() => { setScope('CENTER'); changed(); }} />
            센터 전체 수강생
          </label>
          <label className="adm-radio">
            <input type="radio" name="scope" checked={scope === 'COURSE'} onChange={() => { setScope('COURSE'); changed(); }} />
            강좌 선택
          </label>
        </fieldset>
        {scope === 'COURSE' && (
          <fieldset>
            <legend className="adm-legend">강좌</legend>
            {options.data?.courses.map((course) => (
              <label key={course.id} className="adm-radio">
                <input type="checkbox" checked={courseIds.includes(course.id)} onChange={() => { setCourseIds(toggle(courseIds, course.id)); changed(); }} />
                {course.name}
              </label>
            ))}
            {err('courseIds') && <p className="adm-field-error">{err('courseIds')}</p>}
          </fieldset>
        )}
        <fieldset>
          <legend className="adm-legend">대상 상태</legend>
          {STATUSES.map((status) => (
            <label key={status} className="adm-radio">
              <input type="checkbox" checked={statuses.includes(status)} onChange={() => { setStatuses(toggle(statuses, status)); changed(); }} />
              {SMS_AUDIENCE[status]}
            </label>
          ))}
          {err('statuses') && <p className="adm-field-error">{err('statuses')}</p>}
        </fieldset>
        <div className="adm-field full">
          <label htmlFor="sms-content">문안</label>
          <div>
            <textarea id="sms-content" rows={3} aria-describedby="sms-bytes" aria-invalid={err('content') ? true : undefined} value={content} onChange={(event) => { setContent(event.target.value); changed(); }} />
            <p id="sms-bytes" className="adm-field-hint" aria-live="polite">
              {bytes}/{MAX_BYTES}byte · SMS
            </p>
            {err('content') && <p className="adm-field-error">{err('content')}</p>}
          </div>
        </div>
        {previewMutation.isError && Object.keys(server).length === 0 && (
          <p className="adm-message error" role="alert">
            {errorMessage(previewMutation.error)}
          </p>
        )}
        <div className="adm-actions">
          <button className="adm-button" type="submit" disabled={previewMutation.isPending}>
            미리보기
          </button>
          <Link className="adm-button secondary" to="/sys/sms?kind=MANUAL">
            목록
          </Link>
        </div>
      </form>

      {stale && (
        <p className="adm-message error" role="alert">
          수신 대상이 바뀌었습니다. 아래 수신자 수를 다시 확인해 주세요.
        </p>
      )}
      {preview && (
        <section className="adm-panel" aria-labelledby="sms-preview">
          <div className="adm-panel-head">
            <h2 id="sms-preview">미리보기</h2>
          </div>
          <p>
            수신자 {preview.recipientCount}명 (중복 제거 {preview.duplicateRemoved}명) · 센터 {preview.centerName} · 강좌 {preview.courseCount}개
          </p>
          <details>
            <summary>수신자 목록 보기 (마스킹)</summary>
            <ul className="adm-list">
              {preview.recipients.map((recipient, index) => (
                <li key={index}>
                  {recipient.name} {recipient.phone}
                </li>
              ))}
            </ul>
          </details>
          <label className="adm-radio">
            <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            수신 대상과 문안을 최종 확인했습니다
          </label>
          {sendMutation.isError && !isStateConflict(sendMutation.error) && (
            <p className="adm-message error" role="alert">
              {Object.values(fieldErrors(sendMutation.error)).join(' ') || errorMessage(sendMutation.error)}
            </p>
          )}
          <div className="adm-actions">
            <button className="adm-button" type="button" disabled={!confirmed || sendMutation.isPending || preview.recipientCount === 0} onClick={() => sendMutation.mutate()}>
              발송 요청
            </button>
          </div>
        </section>
      )}
    </>
  );
}