// 교육기수 등록·수정 화면. 날짜 순서와 연결 강좌 영향은 서버 검사와 안내 문구로 알린다 (ADM-EDU-002P)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { createCycle, updateCycle, type CycleWrite } from '../../api/education';
import { cycleQuery, type Cycle } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { CYCLE_STATUS } from '../../lib/labels';
import { isVersionConflict } from '../../lib/messages';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

const BLANK: Record<keyof CycleWrite, string> = {
  name: '',
  year: '',
  order: '',
  receptionStart: '',
  receptionEnd: '',
  educationStart: '',
  educationEnd: '',
  status: 'DRAFT',
};

const fromCycle = (cycle: Cycle): Record<keyof CycleWrite, string> => ({
  name: cycle.name,
  year: String(cycle.year),
  order: String(cycle.order),
  receptionStart: cycle.receptionStart,
  receptionEnd: cycle.receptionEnd,
  educationStart: cycle.educationStart,
  educationEnd: cycle.educationEnd,
  status: cycle.status,
});

export function CycleFormPage({ mode }: { mode: 'create' | 'edit' }) {
  const { cycleId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery({ ...cycleQuery(cycleId), enabled: mode === 'edit' });
  if (mode === 'create') return <CycleForm key="new" mode="create" initial={BLANK} />;
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return <CycleForm key={data.cycleId} mode="edit" initial={fromCycle(data)} cycle={data} />;
}

function CycleForm({ mode, initial, cycle }: { mode: 'create' | 'edit'; initial: Record<keyof CycleWrite, string>; cycle?: Cycle }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const [values, setValues] = useState(initial);
  const [missing, setMissing] = useState<Partial<Record<keyof CycleWrite, string>>>({});
  const [saved, setSaved] = useState(false);

  const mutation = useMutation({
    mutationFn: (body: CycleWrite) => (cycle ? updateCycle(cycle.cycleId, { ...body, version: cycle.version }) : createCycle(body, key.current())),
    onSuccess: (result) => {
      key.renew();
      queryClient.removeQueries({ queryKey: ['cycles'] });
      queryClient.removeQueries({ queryKey: ['course-options'] });
      if (mode === 'create') void navigate(`/edu/cycles/${result.cycleId}`, { replace: true });
      else {
        queryClient.setQueryData(cycleQuery(result.cycleId).queryKey, result);
        setSaved(true);
      }
    },
  });

  const set = (name: keyof CycleWrite) => (event: { target: { value: string } }) => {
    setSaved(false);
    setValues((current) => ({ ...current, [name]: event.target.value }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Partial<Record<keyof CycleWrite, string>> = {};
    for (const name of Object.keys(BLANK) as Array<keyof CycleWrite>) {
      if (!values[name].trim()) errors[name] = '필수 항목입니다.';
    }
    setMissing(errors);
    if (Object.keys(errors).length > 0) return;
    mutation.mutate({
      ...values,
      year: Number(values.year),
      order: Number(values.order),
      status: values.status as CycleWrite['status'],
    });
  };

  const server = fieldErrors(mutation.error);
  const err = (name: keyof CycleWrite) => missing[name] ?? server[name];

  return (
    <>
      <div className="adm-page-heading">
        <h1>{mode === 'create' ? '교육기수 등록' : '교육기수 수정'}</h1>
      </div>
      <form className="adm-form" aria-label="교육기수" noValidate onSubmit={submit}>
        <div className="adm-form-grid">
          <Field id="cycle-name" label="기수명" required error={err('name')}>
            <input {...describe('cycle-name', err('name'))} value={values.name} maxLength={50} onChange={set('name')} />
          </Field>
          <Field id="cycle-year" label="교육연도" required error={err('year')}>
            <input {...describe('cycle-year', err('year'))} type="number" min={2020} max={2100} value={values.year} onChange={set('year')} />
          </Field>
          <Field id="cycle-order" label="차수" required error={err('order')}>
            <input {...describe('cycle-order', err('order'))} type="number" min={1} value={values.order} onChange={set('order')} />
          </Field>
          <Field id="cycle-status" label="사용 상태" required error={err('status')}>
            <select {...describe('cycle-status', err('status'))} value={values.status} onChange={set('status')}>
              {Object.entries(CYCLE_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field id="cycle-reception-start" label="모집 시작일" required error={err('receptionStart')}>
            <input {...describe('cycle-reception-start', err('receptionStart'))} type="date" value={values.receptionStart} onChange={set('receptionStart')} />
          </Field>
          <Field id="cycle-reception-end" label="모집 종료일" required error={err('receptionEnd')}>
            <input {...describe('cycle-reception-end', err('receptionEnd'))} type="date" value={values.receptionEnd} onChange={set('receptionEnd')} />
          </Field>
          <Field id="cycle-education-start" label="교육 시작일" required error={err('educationStart')}>
            <input {...describe('cycle-education-start', err('educationStart'))} type="date" value={values.educationStart} onChange={set('educationStart')} />
          </Field>
          <Field id="cycle-education-end" label="교육 종료일" required error={err('educationEnd')}>
            <input {...describe('cycle-education-end', err('educationEnd'))} type="date" value={values.educationEnd} onChange={set('educationEnd')} />
          </Field>
        </div>
        {cycle && cycle.courseCount > 0 && (
          <p className="adm-notice">
            이 기수에 연결된 강좌가 {cycle.courseCount}건 있습니다. 기간을 바꾸면 해당 강좌의 접수·교육 기간에 영향이 있는지 확인해 주세요.
          </p>
        )}
        {saved && (
          <p className="adm-message" role="status">
            저장했습니다.
          </p>
        )}
        {mutation.isError && (
          <p className="adm-message error" role="alert">
            {isVersionConflict(mutation.error)
              ? '다른 곳에서 먼저 수정되었습니다. 목록으로 돌아가 최신 내용을 다시 열어 주세요.'
              : errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          <button className="adm-button" type="submit" disabled={mutation.isPending}>
            저장
          </button>
          <Link className="adm-button secondary" to="/edu/cycles">
            목록
          </Link>
        </div>
      </form>
    </>
  );
}
