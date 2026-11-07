// 강좌 등록·수정 화면. 공개 요청·접수 마감·폐강 처리 버튼은 서버가 준 가능 여부(actions)대로만 보인다 (ADM-EDU-001P)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  cancelCourse,
  closeCourseReception,
  createCourse,
  publishCourse,
  updateCourse,
  type AdminCourse,
  type CourseWrite,
} from '../../api/education';
import { adminCourseQuery, cancelPreviewQuery, courseOptionsQuery, type CourseOptions } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { OwnerFiles } from '../../components/OwnerFiles';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { fromDateTimeInput, toDateTimeInput } from '../../lib/format';
import { COURSE_STATUS, EDUCATION_STATE, RECEPTION_STATE } from '../../lib/labels';
import { allFieldMessages, isVersionConflict } from '../../lib/messages';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

type Values = Record<keyof CourseWrite, string>;

const BLANK: Values = {
  cycleId: '',
  dongId: '',
  classId: '',
  name: '',
  instructorId: '',
  capacity: '',
  waitCapacity: '',
  tuition: '',
  receptionStart: '',
  receptionEnd: '',
  outsideReceptionStart: '',
  educationStart: '',
  educationEnd: '',
  description: '',
};
// 비워 둘 수 있는 항목은 이 둘뿐이다.
const OPTIONAL: Array<keyof Values> = ['outsideReceptionStart', 'description'];

const fromCourse = (course: AdminCourse): Values => ({
  cycleId: course.cycleId,
  dongId: course.dongId,
  classId: course.classId,
  name: course.name,
  instructorId: course.instructorId,
  capacity: String(course.capacity),
  waitCapacity: String(course.waitCapacity),
  tuition: String(course.tuition),
  receptionStart: toDateTimeInput(course.receptionStart),
  receptionEnd: toDateTimeInput(course.receptionEnd),
  outsideReceptionStart: course.outsideReceptionStart ? toDateTimeInput(course.outsideReceptionStart) : '',
  educationStart: course.educationStart,
  educationEnd: course.educationEnd,
  description: course.description,
});

const toBody = (values: Values): CourseWrite => ({
  ...values,
  capacity: Number(values.capacity),
  waitCapacity: Number(values.waitCapacity),
  tuition: Number(values.tuition),
  receptionStart: fromDateTimeInput(values.receptionStart),
  receptionEnd: fromDateTimeInput(values.receptionEnd),
  outsideReceptionStart: values.outsideReceptionStart ? fromDateTimeInput(values.outsideReceptionStart) : null,
});

export function CourseFormPage({ mode }: { mode: 'create' | 'edit' }) {
  const { courseId = '' } = useParams();
  const options = useQuery(courseOptionsQuery);
  const course = useQuery({ ...adminCourseQuery(courseId), enabled: mode === 'edit' });
  const failed = options.isError ? options.error : course.isError ? course.error : null;
  if (failed) return <p role="alert">{errorMessage(failed)}</p>;
  if (!options.data || (mode === 'edit' && !course.data)) return <p role="status">불러오는 중입니다.</p>;
  const data = course.data;
  return mode === 'edit' && data ? (
    <CourseForm key={data.courseId} options={options.data} course={data} />
  ) : (
    <CourseForm key="new" options={options.data} />
  );
}

function CourseForm({ options, course }: { options: CourseOptions; course?: AdminCourse }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const [values, setValues] = useState<Values>(course ? fromCourse(course) : { ...BLANK, dongId: options.dongs[0]?.id ?? '' });
  const [missing, setMissing] = useState<Partial<Record<keyof Values, string>>>({});
  const [saved, setSaved] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);

  const refreshed = (result: AdminCourse) => {
    queryClient.removeQueries({ queryKey: ['courses', 'list'] });
    queryClient.setQueryData(adminCourseQuery(result.courseId).queryKey, result);
  };

  const save = useMutation({
    mutationFn: (body: CourseWrite) =>
      course ? updateCourse(course.courseId, { ...body, version: course.version }) : createCourse(body, key.current()),
    onSuccess: (result) => {
      key.renew();
      refreshed(result);
      if (course) setSaved(true);
      else void navigate(`/edu/courses/${result.courseId}`, { replace: true });
    },
  });
  const action = useMutation({
    mutationFn: (run: () => Promise<AdminCourse>) => run(),
    onSuccess: (result) => {
      refreshed(result);
      setCancelOpen(false);
    },
  });

  const set = (name: keyof Values) => (event: { target: { value: string } }) => {
    setSaved(false);
    setValues((current) => ({ ...current, [name]: event.target.value }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Partial<Record<keyof Values, string>> = {};
    for (const name of Object.keys(BLANK) as Array<keyof Values>) {
      if (!OPTIONAL.includes(name) && !values[name].trim()) errors[name] = '필수 항목입니다.';
    }
    setMissing(errors);
    if (Object.keys(errors).length === 0) save.mutate(toBody(values));
  };

  const server = fieldErrors(save.error);
  const err = (name: keyof Values) => missing[name] ?? server[name];
  const actions = course?.actions;
  const readOnly = course !== undefined && !actions?.canEdit;
  const select = (name: keyof Values, label: string, items: Array<{ id: string; name: string }>) => {
    const id = `course-${name}`;
    return (
      <Field id={id} label={label} required error={err(name)}>
        <select {...describe(id, err(name))} value={values[name]} onChange={set(name)}>
          <option value="">선택</option>
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </Field>
    );
  };
  const input = (name: keyof Values, label: string, type: string, extra: { hint?: string; required?: boolean } = {}) => {
    const id = `course-${name}`;
    return (
      <Field id={id} label={label} required={extra.required ?? !OPTIONAL.includes(name)} error={err(name)} hint={extra.hint}>
        <input {...describe(id, err(name), extra.hint)} type={type} value={values[name]} onChange={set(name)} />
      </Field>
    );
  };

  return (
    <>
      <div className="adm-page-heading">
        <h1>{course ? '강좌 수정' : '강좌 등록'}</h1>
      </div>
      <p className="adm-state">
        상태: {course ? COURSE_STATUS[course.status] : '작성중'}
        {course && ` · ${RECEPTION_STATE[course.receptionState]} · ${EDUCATION_STATE[course.educationState]}`}
      </p>
      <form className="adm-form" aria-label="강좌" noValidate onSubmit={submit}>
        <fieldset disabled={readOnly}>
          <h2 className="adm-section">기본</h2>
          <div className="adm-form-grid">
            {select('cycleId', '기수', options.cycles)}
            {select('dongId', '운영 동', options.dongs)}
            {select('classId', '분류', options.classes)}
            {select('instructorId', '대표강사', options.instructors)}
            <Field id="course-name" label="강좌명" required error={err('name')} full>
              <input {...describe('course-name', err('name'))} value={values.name} maxLength={100} onChange={set('name')} />
            </Field>
          </div>
          <h2 className="adm-section">접수·정원</h2>
          <div className="adm-form-grid">
            {course && (
              <Field id="course-official" label="공고 모집정원" hint="공고 기준이며 고칠 수 없습니다.">
                <p>{course.officialCapacity === null ? '공고에 없음' : `${course.officialCapacity}명`}</p>
              </Field>
            )}
            {course && (
              <Field id="course-status-now" label="현재 점유·대기">
                <p>
                  점유 {course.occupied}명 · 대기 {course.waiting}명
                </p>
              </Field>
            )}
            {input('capacity', '모집정원', 'number', { hint: course ? '현재 점유보다 작게 줄일 수 없습니다.' : undefined })}
            {input('waitCapacity', '대기정원', 'number')}
            {input('tuition', '수강료(원)', 'number')}
            {input('receptionStart', '접수 시작', 'datetime-local')}
            {input('receptionEnd', '접수 종료', 'datetime-local')}
            {input('outsideReceptionStart', '관외 접수 시작', 'datetime-local', {
              hint: '접수 시작 이상, 접수 종료 미만. 비우면 관외 접수를 받지 않습니다.',
            })}
            {input('educationStart', '교육 시작일', 'date')}
            {input('educationEnd', '교육 종료일', 'date')}
          </div>
          <h2 className="adm-section">내용</h2>
          <div className="adm-form-grid">
            <Field id="course-description" label="강의내용" error={err('description')} full hint="대상, 준비물, 회차 내용은 본문에 적습니다.">
              <textarea
                {...describe('course-description', err('description'), '대상, 준비물, 회차 내용은 본문에 적습니다.')}
                rows={6}
                maxLength={4000}
                value={values.description}
                onChange={set('description')}
              />
            </Field>
          </div>
        </fieldset>
        {course && (
          <>
            <h2 className="adm-section">일정</h2>
            <p>
              등록 {course.scheduleCount}건 · <Link to={`/edu/schedules?courseId=${course.courseId}`}>일정 관리</Link>
            </p>
          </>
        )}
        {saved && (
          <p className="adm-message" role="status">
            저장했습니다.
          </p>
        )}
        {save.isError && (
          <p className="adm-message error" role="alert">
            {isVersionConflict(save.error)
              ? '다른 곳에서 먼저 수정되었습니다. 목록으로 돌아가 최신 내용을 다시 열어 주세요.'
              : errorMessage(save.error)}
          </p>
        )}
        {action.isError && (
          <p className="adm-message error" role="alert">
            {allFieldMessages(action.error) || errorMessage(action.error)}
          </p>
        )}
        <div className="adm-actions">
          {!readOnly && (
            <button className="adm-button" type="submit" disabled={save.isPending}>
              저장
            </button>
          )}
          {course && actions?.canPublish && (
            <button className="adm-button secondary" type="button" disabled={action.isPending} onClick={() => action.mutate(() => publishCourse(course.courseId))}>
              공개 요청
            </button>
          )}
          {course && actions?.canCloseReception && (
            <button className="adm-button secondary" type="button" disabled={action.isPending} onClick={() => action.mutate(() => closeCourseReception(course.courseId))}>
              접수 마감
            </button>
          )}
          {course && actions?.canCancel && (
            <button className="adm-button danger" type="button" onClick={() => setCancelOpen(true)}>
              폐강 처리
            </button>
          )}
          <Link className="adm-button secondary" to="/edu/courses">
            목록
          </Link>
        </div>
      </form>
      {course ? <OwnerFiles ownerPath={`/courses/${course.courseId}`} label="강의계획서" /> : <p className="adm-notice">강의계획서 파일은 강좌를 저장한 뒤에 추가할 수 있습니다.</p>}
      {course && (
        <CancelDialog
          open={cancelOpen}
          course={course}
          pending={action.isPending}
          error={action.isError ? allFieldMessages(action.error) || errorMessage(action.error) : null}
          onClose={() => setCancelOpen(false)}
          onConfirm={(reason) => action.mutate(() => cancelCourse(course.courseId, reason))}
        />
      )}
    </>
  );
}

interface CancelDialogProps {
  open: boolean;
  course: AdminCourse;
  pending: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}

function CancelDialog({ open, course, pending, error, onClose, onConfirm }: CancelDialogProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState('');
  const preview = useQuery({ ...cancelPreviewQuery(course.courseId), enabled: open });

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  return (
    <dialog ref={dialog} className="adm-dialog" aria-labelledby="cancel-title" onClose={onClose}>
      <div className="adm-dialog-head">
        <h2 id="cancel-title">폐강 처리</h2>
      </div>
      <div className="adm-dialog-context">
        <p>
          <strong>{course.name}</strong>을(를) 폐강합니다.
        </p>
        {preview.data && (
          <p>
            신청 {preview.data.applicationCount}건, 결제 {preview.data.paidCount}건이 영향을 받습니다.
          </p>
        )}
        <p>폐강은 환불 완료가 아닙니다. 신청 취소와 환불·알림은 별도 절차로 진행됩니다.</p>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onConfirm(reason.trim());
        }}
      >
        <div className="adm-form-grid">
          <Field id="cancel-reason" label="폐강 사유" required full>
            <textarea id="cancel-reason" rows={3} maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} />
          </Field>
        </div>
        {error && (
          <p className="adm-message error" role="alert">
            {error}
          </p>
        )}
        <div className="adm-dialog-actions">
          <button className="adm-button secondary" type="button" onClick={onClose}>
            닫기
          </button>
          <button className="adm-button danger" type="submit" disabled={pending || !reason.trim()}>
            폐강 처리
          </button>
        </div>
      </form>
    </dialog>
  );
}
