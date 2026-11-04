// 휴강·보강 등록 화면. 휴강은 수업일과 사유만, 보강은 시설과 시간도 함께 입력한다 (ADM-EDU-003P)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { createScheduleChange, type ScheduleChangeWrite } from '../../api/campus';
import { adminCourseQuery, courseOptionsQuery } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { CHANGE_KIND } from '../../lib/labels';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

interface Values {
  classDate: string;
  kind: ScheduleChangeWrite['kind'];
  facilityId: string;
  startTime: string;
  endTime: string;
  reason: string;
}

export function ScheduleChangeFormPage() {
  const { courseId = '' } = useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const course = useQuery(adminCourseQuery(courseId));
  const options = useQuery(courseOptionsQuery);
  const [values, setValues] = useState<Values>({ classDate: '', kind: 'CANCEL', facilityId: '', startTime: '', endTime: '', reason: '' });
  const [missing, setMissing] = useState<Partial<Record<keyof Values, string>>>({});
  const makeup = values.kind === 'MAKEUP';

  const mutation = useMutation({
    mutationFn: (body: ScheduleChangeWrite) => createScheduleChange(courseId, body, key.current()),
    onSuccess: () => {
      key.renew();
      queryClient.removeQueries({ queryKey: ['schedules'] });
      void navigate(`/edu/schedules?courseId=${courseId}`, { replace: true });
    },
  });

  const failed = course.isError ? course.error : options.isError ? options.error : null;
  if (failed) return <p role="alert">{errorMessage(failed)}</p>;
  if (!course.data || !options.data) return <p role="status">불러오는 중입니다.</p>;

  const set = (name: keyof Values) => (event: { target: { value: string } }) => setValues((current) => ({ ...current, [name]: event.target.value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Partial<Record<keyof Values, string>> = {};
    const required: Array<keyof Values> = makeup ? ['classDate', 'reason', 'facilityId', 'startTime', 'endTime'] : ['classDate', 'reason'];
    for (const name of required) if (!values[name].trim()) errors[name] = '필수 항목입니다.';
    setMissing(errors);
    if (Object.keys(errors).length > 0) return;
    mutation.mutate({
      classDate: values.classDate,
      kind: values.kind,
      reason: values.reason.trim(),
      facilityId: makeup ? values.facilityId : null,
      startTime: makeup ? values.startTime : null,
      endTime: makeup ? values.endTime : null,
    });
  };

  const server = fieldErrors(mutation.error);
  const err = (name: keyof Values) => missing[name] ?? server[name];

  return (
    <>
      <div className="adm-page-heading">
        <h1>휴보강 등록</h1>
      </div>
      <p className="adm-state">강좌: {course.data.name}</p>
      <form className="adm-form" aria-label="휴보강" noValidate onSubmit={submit}>
        <div className="adm-form-grid">
          <Field id="change-kind" label="구분" required>
            <select {...describe('change-kind')} value={values.kind} onChange={set('kind')}>
              {Object.entries(CHANGE_KIND).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field id="change-date" label="수업일" required error={err('classDate')}>
            <input {...describe('change-date', err('classDate'))} type="date" value={values.classDate} onChange={set('classDate')} />
          </Field>
          {makeup && (
            <>
              <Field id="change-facility" label="보강 시설" required error={err('facilityId')}>
                <select {...describe('change-facility', err('facilityId'))} value={values.facilityId} onChange={set('facilityId')}>
                  <option value="">선택</option>
                  {options.data.rooms.map((room) => (
                    <option key={room.id} value={room.id}>
                      {room.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field id="change-start" label="보강 시작 시각" required error={err('startTime')}>
                <input {...describe('change-start', err('startTime'))} type="time" value={values.startTime} onChange={set('startTime')} />
              </Field>
              <Field id="change-end" label="보강 종료 시각" required error={err('endTime')}>
                <input {...describe('change-end', err('endTime'))} type="time" value={values.endTime} onChange={set('endTime')} />
              </Field>
            </>
          )}
          <Field id="change-reason" label="사유" required error={err('reason')} full>
            <input {...describe('change-reason', err('reason'))} value={values.reason} maxLength={200} onChange={set('reason')} />
          </Field>
        </div>
        {mutation.isError && Object.keys(server).length === 0 && (
          <p className="adm-message error" role="alert">
            {errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          <button className="adm-button" type="submit" disabled={mutation.isPending}>
            저장
          </button>
          <Link className="adm-button secondary" to={`/edu/schedules?courseId=${courseId}`}>
            목록
          </Link>
        </div>
      </form>
    </>
  );
}