// 강좌 관리 목록 화면. 조건은 주소의 쿼리에 두어 새로 고침·뒤로 가기에도 유지한다 (ADM-EDU-001)
import { useQuery } from '@tanstack/react-query';
import type { Schemas } from '@jori/api-client';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { adminCourseListQuery, courseOptionsQuery, type AdminCourseParams } from '../../api/queries';
import { CsvButton } from '../../components/CsvButton';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDate, won } from '../../lib/format';
import { COURSE_STATUS, RECEPTION_STATE } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';
import { useHasAuthority } from '../../layout/menu';

const PAGE_SIZE = 20;
const FILTERS = ['q', 'cycleId', 'classId', 'dongId', 'status'] as const;

export function CourseListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: AdminCourseParams = {
    q: params.get('q') ?? undefined,
    cycleId: params.get('cycleId') ?? undefined,
    classId: params.get('classId') ?? undefined,
    dongId: params.get('dongId') ?? undefined,
    status: (params.get('status') as Schemas['CourseAdminStatus'] | null) ?? undefined,
    page,
  };
  const list = useQuery(adminCourseListQuery(filters));
  const options = useQuery(courseOptionsQuery);
  const canCreate = useHasAuthority('AU.CORS_W');

  const search = (form: HTMLFormElement) => {
    const data = new FormData(form);
    const next = Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()]));
    void navigate(`/edu/courses${toQueryString(next)}`);
  };
  const hrefFor = (next: number) =>
    `/edu/courses${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>강좌 관리</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>강좌 관리 목록</h2>
          {canCreate && (
            <Link className="adm-button" to="/edu/courses/new">
              등록
            </Link>
          )}
        </div>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="강좌 검색"
          onSubmit={(event) => {
            event.preventDefault();
            search(event.currentTarget);
          }}
        >
          <label className="wide">
            검색어
            <input name="q" defaultValue={filters.q} placeholder="강좌명으로 검색" maxLength={100} />
          </label>
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
          <label>
            분류
            <select name="classId" defaultValue={filters.classId ?? ''}>
              <option value="">전체 분류</option>
              {options.data?.classes.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            운영 동
            <select name="dongId" defaultValue={filters.dongId ?? ''}>
              <option value="">전체 동</option>
              {options.data?.dongs.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            상태
            <select name="status" defaultValue={filters.status ?? ''}>
              <option value="">전체 상태</option>
              {Object.entries(COURSE_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/edu/courses">
            조건 지우기
          </Link>
          <CsvButton path="/courses/export.csv" query={toQueryString(Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])))} />
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="강좌 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">강좌명</th>
                    <th scope="col">기수</th>
                    <th scope="col">분류</th>
                    <th scope="col">강사</th>
                    <th scope="col">접수기간</th>
                    <th scope="col">정원 / 점유 / 대기</th>
                    <th scope="col">수강료</th>
                    <th scope="col">상태</th>
                    <th scope="col">관리</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((course) => (
                    <tr key={course.courseId}>
                      <td>
                        <Link to={`/edu/courses/${course.courseId}`}>{course.name}</Link>
                      </td>
                      <td>{course.cycleName}</td>
                      <td>{course.className ?? '미분류'}</td>
                      <td>{course.instructorName}</td>
                      <td>
                        {kstDate(course.receptionStart)} ~ {kstDate(course.receptionEnd)}
                      </td>
                      <td>
                        {course.capacity} / {course.occupied} / {course.waiting}
                      </td>
                      <td>{won(course.tuition)}</td>
                      <td>
                        {COURSE_STATUS[course.status]}
                        <span className="adm-sub">{RECEPTION_STATE[course.receptionState]}</span>
                      </td>
                      <td>
                        <Link className="adm-button secondary" to={`/edu/courses/${course.courseId}`} aria-label={`상세 (${course.name})`}>
                          상세
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 강좌가 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}
