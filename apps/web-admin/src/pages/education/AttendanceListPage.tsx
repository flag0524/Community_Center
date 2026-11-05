// 출석 현황 목록 화면. 조회 전용이며 CSV로 내려받을 수 없다 (ADM-EDU-006)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { attendanceListQuery, courseOptionsQuery, type AttendanceParams } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { INPUT_STATUS } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['cycleId', 'courseId', 'classDate', 'inputStatus'] as const;

export function AttendanceListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: AttendanceParams = {
    cycleId: params.get('cycleId') ?? undefined,
    courseId: params.get('courseId') ?? undefined,
    classDate: params.get('classDate') ?? undefined,
    inputStatus: (params.get('inputStatus') as Schemas['AttendanceInputStatus'] | null) ?? undefined,
    page,
  };
  const list = useQuery(attendanceListQuery(filters));
  const options = useQuery(courseOptionsQuery);

  const hrefFor = (next: number) =>
    `/edu/attendance${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>출석 현황</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>출석 현황 목록</h2>
        </div>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="출석 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const next = Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()]));
            void navigate(`/edu/attendance${toQueryString(next)}`);
          }}
        >
          <label>
            기수
            <select name="cycleId" defaultValue={filters.cycleId ?? ''}>
              <option value="">전체 기수</option>
              {options.data?.cycles.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="wide">
            강좌
            <select name="courseId" defaultValue={filters.courseId ?? ''}>
              <option value="">전체 강좌</option>
              {options.data?.courses.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            수업일
            <input name="classDate" type="date" defaultValue={filters.classDate} />
          </label>
          <label>
            입력 상태
            <select name="inputStatus" defaultValue={filters.inputStatus ?? ''}>
              <option value="">전체</option>
              {Object.entries(INPUT_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/edu/attendance">
            조건 지우기
          </Link>
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="출석 현황 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">강좌</th>
                    <th scope="col">수업일</th>
                    <th scope="col">회차</th>
                    <th scope="col">강사</th>
                    <th scope="col">출석 / 결석 / 미체크</th>
                    <th scope="col">입력상태</th>
                    <th scope="col">관리</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((sheet) => (
                    <tr key={sheet.attendanceId}>
                      <td>
                        <Link to={`/edu/attendance/${sheet.attendanceId}`}>{sheet.courseName}</Link>
                      </td>
                      <td>{sheet.classDate}</td>
                      <td>{sheet.session}회차</td>
                      <td>{sheet.instructorName}</td>
                      <td>
                        {sheet.present} / {sheet.absent} / {sheet.unchecked}
                      </td>
                      <td>{INPUT_STATUS[sheet.inputStatus]}</td>
                      <td>
                        <Link className="adm-button secondary" to={`/edu/attendance/${sheet.attendanceId}`} aria-label={`상세 (${sheet.courseName} ${sheet.classDate})`}>
                          상세
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 출석부가 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
        <p className="adm-notice">출석 현황은 조회만 할 수 있으며 CSV로 내려받을 수 없습니다.</p>
      </section>
    </>
  );
}
