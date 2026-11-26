// 강사 출석 입력. 담당 강좌의 수업 회차를 골라 출석·결석·미체크를 표시하고 확인한 뒤 저장한다 (USR-TCH-007, FN-064)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiRequestError } from '../../api/http';
import { teachingCoursesQuery, teachingSheetQuery } from '../../api/queries';
import {
  createTeachingSheet,
  updateTeachingSheet,
  type AttendanceMark,
  type TeachingCourse,
  type TeachingSession,
  type TeachingSheet,
} from '../../api/teaching';
import { FormMessage } from '../../components/FormMessage';
import { QueryFallback } from '../../components/QueryFallback';
import { MyPageLayout } from '../../layout/SubLayout';
import { errorMessage } from '../../lib/errors';
import { formatDate } from '../../lib/format';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '강의 출석 입력';
const MARKS: Array<[AttendanceMark, string]> = [
  ['PRESENT', '출석'],
  ['ABSENT', '결석'],
  ['UNCHECKED', '미체크'],
];
const STATUS: Record<TeachingSession['status'], string> = { NOT_STARTED: '미입력', IN_PROGRESS: '입력중', DONE: '완료' };

const lessonKey = (item: TeachingSession) => `${item.classDate}.${item.scheduleId}.${item.changeId ?? ''}`;
const lessonLabel = (item: TeachingSession) =>
  `${formatDate(item.classDate)} ${item.session}회차 ${item.startTime}${item.makeup ? ' · 보강' : ''} · ${STATUS[item.status]}`;

function RosterForm({ sheet, onSaved, onReload }: { sheet: TeachingSheet; onSaved: (saved: TeachingSheet) => void; onReload: () => void }) {
  const [marks, setMarks] = useState<Record<string, AttendanceMark>>(() =>
    Object.fromEntries(sheet.roster.map((entry) => [entry.applicationId, entry.mark])),
  );
  const [confirmed, setConfirmed] = useState(false);
  // 같은 내용을 다시 보내면 같은 키라 두 번 저장되지 않는다. 표시를 바꾸면 새 키를 쓴다.
  const idempotencyKey = useRef(crypto.randomUUID());
  const sending = useRef(false);

  const save = useMutation({
    mutationFn: () => {
      const body = {
        confirmed,
        marks: sheet.roster.map((entry) => ({ applicationId: entry.applicationId, mark: marks[entry.applicationId]! })),
      };
      if (sheet.attendanceId) return updateTeachingSheet(sheet.attendanceId, { ...body, version: sheet.version! });
      const { courseId, classDate, scheduleId, changeId } = sheet;
      return createTeachingSheet({ ...body, courseId, classDate, scheduleId, changeId }, idempotencyKey.current);
    },
    onSuccess: onSaved,
    onSettled: () => {
      sending.current = false;
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!confirmed || sending.current) return;
    sending.current = true;
    save.mutate();
  }

  function mark(applicationId: string, value: AttendanceMark) {
    idempotencyKey.current = crypto.randomUUID();
    setMarks((before) => ({ ...before, [applicationId]: value }));
  }

  const count = (value: AttendanceMark) => Object.values(marks).filter((item) => item === value).length;
  const conflict = save.error instanceof ApiRequestError && save.error.status === 409;

  if (sheet.roster.length === 0) {
    return (
      <div className="empty-state">
        <h3>수강생이 없습니다.</h3>
      </div>
    );
  }
  return (
    <form noValidate onSubmit={submit}>
      <div className="table-wrap">
        <table className="data-table" aria-label="출석 명단">
          <thead>
            <tr>
              <th scope="col">이름</th>
              <th scope="col">신청번호</th>
              {MARKS.map(([value, label]) => (
                <th key={value} scope="col">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.roster.map((entry) => (
              <tr key={entry.applicationId}>
                <td data-label="이름">{entry.name}</td>
                <td data-label="신청번호">{entry.applicationId}</td>
                {MARKS.map(([value, label]) => (
                  <td key={value} data-label={label}>
                    <label className="attendance-choice">
                      <input
                        type="radio"
                        name={`mark-${entry.applicationId}`}
                        aria-label={`${entry.name} ${entry.applicationId} ${label}`}
                        checked={marks[entry.applicationId] === value}
                        onChange={() => mark(entry.applicationId, value)}
                      />
                    </label>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p role="status">
        합계 출석 {count('PRESENT')} · 결석 {count('ABSENT')} · 미체크 {count('UNCHECKED')}
      </p>
      <label className="proto-check">
        <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
        입력 내용을 확인했습니다
      </label>
      <div className="proto-actions">
        <button className="button" type="submit" disabled={!confirmed || save.isPending}>
          저장
        </button>
        {conflict ? (
          <button className="button secondary" type="button" onClick={onReload}>
            다시 불러오기
          </button>
        ) : null}
      </div>
      <FormMessage text={save.isError ? errorMessage(save.error) : ''} error />
    </form>
  );
}

function SheetPanel({ course, lesson }: { course: TeachingCourse; lesson: TeachingSession }) {
  const queryClient = useQueryClient();
  const options = teachingSheetQuery(course.courseId, lesson);
  const query = useQuery(options);
  const [saved, setSaved] = useState(false);
  const [reloads, setReloads] = useState(0);
  const sheet = query.data;
  if (!sheet) return <QueryFallback query={query} what="출석 명단" />;

  return (
    <>
      <FormMessage text={saved ? '출석을 저장했습니다.' : ''} />
      {/* 저장하거나 다시 불러오면 서버의 값으로 입력 칸을 새로 채운다 */}
      <RosterForm
        key={`${sheet.version ?? 0}-${reloads}`}
        sheet={sheet}
        onSaved={(next) => {
          queryClient.setQueryData(options.queryKey, next);
          setSaved(true);
          void queryClient.invalidateQueries({ queryKey: teachingCoursesQuery.queryKey });
        }}
        onReload={() => {
          setSaved(false);
          void query.refetch().then(() => setReloads((count) => count + 1));
        }}
      />
    </>
  );
}

export function TeachingAttendancePage() {
  usePageTitle(TITLE);
  const [params, setParams] = useSearchParams();
  const query = useQuery(teachingCoursesQuery);
  const data = query.data;
  if (!data) return <QueryFallback query={query} what="담당 강좌" />;

  const course = data.items.find((item) => item.courseId === params.get('course')) ?? data.items[0];
  const lesson = course?.sessions.find((item) => lessonKey(item) === params.get('lesson')) ?? course?.sessions[0];

  return (
    <MyPageLayout title={TITLE} crumbs={[{ label: '마이페이지' }, { label: TITLE }]}>
      <div className="proto">
        {!course ? (
          <div className="empty-state">
            <h3>담당 강좌가 없습니다.</h3>
            <p>센터에서 강좌를 배정하면 여기에서 출석을 입력할 수 있습니다.</p>
          </div>
        ) : (
          <>
            <div className="proto-form">
              <label className="field">
                담당 강좌
                <select value={course.courseId} onChange={(event) => setParams({ course: event.target.value }, { replace: true })}>
                  {data.items.map((item) => (
                    <option key={item.courseId} value={item.courseId}>
                      {item.courseName}
                    </option>
                  ))}
                </select>
              </label>
              {lesson ? (
                <label className="field">
                  수업일
                  <select
                    value={lessonKey(lesson)}
                    onChange={(event) => setParams({ course: course.courseId, lesson: event.target.value }, { replace: true })}
                  >
                    {course.sessions.map((item) => (
                      <option key={lessonKey(item)} value={lessonKey(item)}>
                        {lessonLabel(item)}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </div>
            {lesson ? (
              <SheetPanel key={`${course.courseId}.${lessonKey(lesson)}`} course={course} lesson={lesson} />
            ) : (
              <div className="empty-state">
                <h3>아직 입력할 수업이 없습니다.</h3>
              </div>
            )}
          </>
        )}
      </div>
    </MyPageLayout>
  );
}
