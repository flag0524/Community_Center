// 강사 심사 목록 화면. 심사 상태·공개 상태·검색어 조건은 주소의 쿼리에 둔다 (ADM-EDU-004)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { instructorReviewListQuery, type InstructorReviewParams } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { REVIEW_STATUS } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['q', 'status', 'isPublic'] as const;

export function InstructorReviewListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: InstructorReviewParams = {
    q: params.get('q') ?? undefined,
    status: (params.get('status') as Schemas['ReviewStatus'] | null) ?? undefined,
    isPublic: (params.get('isPublic') as 'true' | 'false' | null) ?? undefined,
    page,
  };
  const list = useQuery(instructorReviewListQuery(filters));

  const hrefFor = (next: number) =>
    `/edu/instructors${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>강사 심사</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>강사 심사 목록</h2>
          <Link className="adm-button" to="/edu/instructors/new">
            방문·외부 접수 등록
          </Link>
        </div>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="강사 심사 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const next = Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()]));
            void navigate(`/edu/instructors${toQueryString(next)}`);
          }}
        >
          <label className="wide">
            검색어
            <input name="q" defaultValue={filters.q} placeholder="지원자 또는 희망 강좌" maxLength={100} />
          </label>
          <label>
            심사 상태
            <select name="status" defaultValue={filters.status ?? ''}>
              <option value="">전체 상태</option>
              {Object.entries(REVIEW_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            공개 상태
            <select name="isPublic" defaultValue={filters.isPublic ?? ''}>
              <option value="">전체</option>
              <option value="true">공개</option>
              <option value="false">비공개</option>
            </select>
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/edu/instructors">
            조건 지우기
          </Link>
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="강사 심사 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">지원번호</th>
                    <th scope="col">지원자</th>
                    <th scope="col">희망 강좌</th>
                    <th scope="col">접수일</th>
                    <th scope="col">심사상태</th>
                    <th scope="col">공개</th>
                    <th scope="col">관리</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((review) => (
                    <tr key={review.applicationId}>
                      <td>{review.applicationId.slice(-6)}</td>
                      <td>
                        <Link to={`/edu/instructors/${review.applicationId}`}>{review.applicantName}</Link>
                      </td>
                      <td>{review.desiredCourse}</td>
                      <td>{review.receivedOn}</td>
                      <td>{REVIEW_STATUS[review.status]}</td>
                      <td>{review.isPublic ? '공개' : '비공개'}</td>
                      <td>
                        <Link className="adm-button secondary" to={`/edu/instructors/${review.applicationId}`} aria-label={`심사 (${review.applicantName})`}>
                          심사
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 지원서가 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}
