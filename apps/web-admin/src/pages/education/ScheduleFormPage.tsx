// 강좌 일정 등록·수정 화면. 같은 시설·요일·시간에 다른 강좌가 있으면 서버가 알려 주는 문구를 시설 항목 아래에 보인다 (ADM-EDU-003P)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { createSchedule, updateSchedule, type Schedule, type ScheduleWrite } from '../../api/campus';
import { adminCourseQuery, courseOptionsQuery, courseSchedulesQuery, type AdminCourse, type CourseOptions } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { WEEKDAY } from '../../lib/labels';
import { isVersionConflict } from '../../lib/messages';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

type Values = Record<keyof ScheduleWrite, string>;

export function ScheduleFormPage({ mode }: { mode: 'create' | 'edit' }) {
  const { courseId = '', scheduleId = '' } = useParams();
  const course = useQuery(adminCourseQuery(courseId));
  const options = useQuery(courseOptionsQuery);
  const schedules = useQuery({ ...courseSchedulesQuery(courseId), enabled: mode === 'edit' });
  const failed = [course, options, schedules].find((query) => query.isError)?.error;
  if (failed) return <p role="alert">{errorMessage(failed)}</p>;
  const own = schedules.data?.schedules.find((item) => item.scheduleId === scheduleId);
  if (!course.data || !options.data || (mode === 'edit' && !schedules.data)) return <p role="status">불러오는 중입니다.</p>;
  if (mode === 'edit' && !own) return <p role="alert">일정을 찾을 수 없습니다.</p>;
  return <ScheduleForm key={scheduleId || 'new'} course={course.data} options={options.data} schedule={own} />;
}

function ScheduleForm({ course, options, schedule }: { course: AdminCourse; options: CourseOptions; schedule?: Schedule }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const [values, setValues] = useState<Values>(
    schedule
      ? {
          weekday: schedule.weekday,
          startTime: schedule.startTime,
          endTime: schedule.endTime,
          facilityId: schedule.facilityId,
          periodStart: schedule.periodStart,
          periodEnd: schedule.periodEnd,
        }
      : { weekday: 'MON', startTime: '', endTime: '', facilityId: '', periodStart: course.educationStart, periodEnd: course.educationEnd },
  );
  const [missing, setMissing] = useState<Partial<Record<keyof Values, string>>>({});

  const mutation = useMutation({
    mutationFn: (body: ScheduleWrite) =>
      schedule ? updateSchedule(course.courseId, schedule.scheduleId, body, schedule.version) : createSchedule(course.courseId, body, key.current()),
    onSuccess: () => {
      key.renew();
      queryClient.removeQueries({ queryKey: ['schedules'] });
      queryClient.removeQueries({ queryKey: ['courses'] });
      void navigate(`/edu/schedules?courseId=${course.courseId}`, { replace: true });
    },
  });

  const set = (name: keyof Values) => (event: { target: { value: string } }) => setValues((current) => ({ ...current, [name]: event.target.value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Partial<Record<keyof Values, string>> = {};
    for (const name of Object.keys(values) as Array<keyof Values>) if (!values[name]) errors[name] = '필수 항목입니다.';
    setMissing(errors);
    if (Object.keys(errors).length === 0) mutation.mutate({ ...values, weekday: values.weekday as ScheduleWrite['weekday'] });
  };

  const server = fieldErrors(mutation.error);
  const err = (name: keyof Values) => missing[name] ?? server[name];
  // 사용을 중지한 강의실에 이미 배정된 일정은 그대로 두고 고칠 수 있게 현재 시설을 선택지에 남긴다.
  const rooms = [...options.rooms];
  if (schedule && !rooms.some((room) => room.id === schedule.facilityId)) rooms.push({ id: schedule.facilityId, name: `${schedule.facilityName} (사용중지)` });

  return (
    <>
      <div className="adm-page-heading">
        <h1>{schedule ? '일정 수정' : '일정 등록'}</h1>
      </div>
      <p className="adm-state">강좌: {course.name}</p>
      <form className="adm-form" aria-label="일정" noValidate onSubmit={submit}>
        <div className="adm-form-grid">
          <Field id="schedule-weekday" label="요일" required error={err('weekday')}>
            <select {...describe('schedule-weekday', err('weekday'))} value={values.weekday} onChange={set('weekday')}>
              {Object.entries(WEEKDAY).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}요일
                </option>
              ))}
            </select>
          </Field>
          <Field id="schedule-facility" label="시설" required error={err('facilityId')} hint="사용 중인 강의실만 고를 수 있습니다.">
            <select {...describe('schedule-facility', err('facilityId'), '사용 중인 강의실만 고를 수 있습니다.')} value={values.facilityId} onChange={set('facilityId')}>
              <option value="">선택</option>
              {rooms.map((room) => (
                <option key={room.id} value={room.id}>
                  {room.name}
                </option>
              ))}
            </select>
          </Field>
          <Field id="schedule-start" label="시작 시각" required error={err('startTime')}>
            <input {...describe('schedule-start', err('startTime'))} type="time" value={values.startTime} onChange={set('startTime')} />
          </Field>
          <Field id="schedule-end" label="종료 시각" required error={err('endTime')}>
            <input {...describe('schedule-end', err('endTime'))} type="time" value={values.endTime} onChange={set('endTime')} />
          </Field>
          <Field id="schedule-period-start" label="적용 시작일" required error={err('periodStart')}>
            <input {...describe('schedule-period-start', err('periodStart'))} type="date" value={values.periodStart} onChange={set('periodStart')} />
          </Field>
          <Field id="schedule-period-end" label="적용 종료일" required error={err('periodEnd')}>
            <input {...describe('schedule-period-end', err('periodEnd'))} type="date" value={values.periodEnd} onChange={set('periodEnd')} />
          </Field>
        </div>
        {mutation.isError && Object.keys(server).length === 0 && (
          <p className="adm-message error" role="alert">
            {isVersionConflict(mutation.error) ? '다른 곳에서 먼저 수정되었습니다. 일정 화면으로 돌아가 다시 열어 주세요.' : errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          <button className="adm-button" type="submit" disabled={mutation.isPending}>
            저장
          </button>
          <Link className="adm-button secondary" to={`/edu/schedules?courseId=${course.courseId}`}>
            목록
          </Link>
        </div>
      </form>
    </>
  );
}
