// 강좌 일정·휴보강 화면. 강좌를 고르면 주간 시간표와 휴보강 목록을 보이고 등록·수정·삭제로 이어진다 (ADM-EDU-003)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { deleteSchedule, deleteScheduleChange } from '../../api/campus';
import { adminCourseListQuery, courseSchedulesQuery } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { CHANGE_KIND, WEEKDAY } from '../../lib/labels';

export function SchedulePage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const courseId = params.get('courseId') ?? '';
  const courses = useQuery(adminCourseListQuery({ size: 100 }));
  const data = useQuery({ ...courseSchedulesQuery(courseId), enabled: courseId !== '' });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: courseSchedulesQuery(courseId).queryKey });
    // 강좌의 일정 수가 달라지므로 강좌 목록·상세도 새로 읽게 한다.
    queryClient.removeQueries({ queryKey: ['courses'] });
  };
  const removeSchedule = useMutation({ mutationFn: (scheduleId: string) => deleteSchedule(courseId, scheduleId), onSuccess: refresh });
  const removeChange = useMutation({ mutationFn: (changeId: string) => deleteScheduleChange(courseId, changeId), onSuccess: refresh });
  const failed = removeSchedule.error ?? removeChange.error;

  return (
    <>
      <div className="adm-page-heading">
        <h1>일정·휴보강</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>강좌 선택</h2>
        </div>
        <form className="adm-toolbar" role="search" aria-label="강좌 선택" onSubmit={(event) => event.preventDefault()}>
          <label className="wide">
            강좌
            <select
              value={courseId}
              onChange={(event) => void navigate(event.target.value ? `/edu/schedules?courseId=${event.target.value}` : '/edu/schedules')}
            >
              <option value="">강좌를 선택하세요</option>
              {courses.data?.items.map((course) => (
                <option key={course.courseId} value={course.courseId}>
                  {course.name}
                </option>
              ))}
            </select>
          </label>
        </form>
        {courses.isError && <p role="alert">{errorMessage(courses.error)}</p>}
      </section>
      {courseId === '' && <p className="adm-notice">일정을 보려면 강좌를 선택해 주세요.</p>}
      {data.isPending && courseId !== '' && <p role="status">불러오는 중입니다.</p>}
      {data.isError && <p role="alert">{errorMessage(data.error)}</p>}
      {failed && (
        <p className="adm-message error" role="alert">
          {errorMessage(failed)}
        </p>
      )}
      {data.data && (
        <>
          <section className="adm-panel">
            <div className="adm-panel-head">
              <h2>주간 시간표</h2>
              {data.data.canEdit && (
                <Link className="adm-button" to={`/edu/schedules/${courseId}/new`}>
                  일정 등록
                </Link>
              )}
            </div>
            <TableWrap label="주간 시간표">
              <table>
                <thead>
                  <tr>
                    <th scope="col">요일</th>
                    <th scope="col">시간</th>
                    <th scope="col">시설</th>
                    <th scope="col">적용 기간</th>
                    {data.data.canEdit && <th scope="col">관리</th>}
                  </tr>
                </thead>
                <tbody>
                  {data.data.schedules.map((schedule) => (
                    <tr key={schedule.scheduleId}>
                      <td>{WEEKDAY[schedule.weekday]}</td>
                      <td>
                        {schedule.startTime}~{schedule.endTime}
                      </td>
                      <td>{schedule.facilityName}</td>
                      <td>
                        {schedule.periodStart} ~ {schedule.periodEnd}
                      </td>
                      {data.data.canEdit && (
                        <td>
                          <Link
                            className="adm-button secondary"
                            to={`/edu/schedules/${courseId}/${schedule.scheduleId}`}
                            aria-label={`수정 (${WEEKDAY[schedule.weekday]}요일 ${schedule.startTime})`}
                          >
                            수정
                          </Link>{' '}
                          <ConfirmButton
                            label="삭제"
                            confirmLabel="정말 삭제"
                            target={`${WEEKDAY[schedule.weekday]}요일 ${schedule.startTime}`}
                            disabled={removeSchedule.isPending}
                            onConfirm={() => removeSchedule.mutate(schedule.scheduleId)}
                          />
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {data.data.schedules.length === 0 && <p>등록된 일정이 없습니다.</p>}
          </section>
          <section className="adm-panel">
            <div className="adm-panel-head">
              <h2>휴강·보강</h2>
              {data.data.canEdit && (
                <Link className="adm-button" to={`/edu/schedules/${courseId}/changes/new`}>
                  휴보강 등록
                </Link>
              )}
            </div>
            <TableWrap label="휴강·보강 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">수업일</th>
                    <th scope="col">구분</th>
                    <th scope="col">시설·시간</th>
                    <th scope="col">사유</th>
                    {data.data.canEdit && <th scope="col">관리</th>}
                  </tr>
                </thead>
                <tbody>
                  {data.data.changes.map((change) => (
                    <tr key={change.changeId}>
                      <td>{change.classDate}</td>
                      <td>{CHANGE_KIND[change.kind]}</td>
                      <td>{change.kind === 'MAKEUP' ? `${change.facilityName} ${change.startTime}~${change.endTime}` : '-'}</td>
                      <td>{change.reason}</td>
                      {data.data.canEdit && (
                        <td>
                          <ConfirmButton
                            label="삭제"
                            confirmLabel="정말 삭제"
                            target={`${change.classDate} ${CHANGE_KIND[change.kind]}`}
                            disabled={removeChange.isPending}
                            onConfirm={() => removeChange.mutate(change.changeId)}
                          />
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {data.data.changes.length === 0 && <p>등록된 휴강·보강이 없습니다.</p>}
          </section>
          <p>
            <Link to={`/edu/courses/${courseId}`}>{data.data.courseName} 강좌로 돌아가기</Link>
          </p>
        </>
      )}
    </>
  );
}
