// 권한 배정 목록 화면. 관리자별로 역할·범위·유효기간과 유효 상태를 보이고 새 배정으로 이어진다 (ADM-SYS-002)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { assignmentListQuery, type AssignmentParams } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { ASSIGNMENT_STATUS } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['status', 'q'] as const;

export function RoleListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: AssignmentParams = { status: (params.get('status') as Schemas['AssignmentStatus'] | null) ?? undefined, q: params.get('q') ?? undefined, page };
  const list = useQuery(assignmentListQuery(filters));
  const hrefFor = (next: number) => `/sys/roles${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>권한 배정</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>배정 목록</h2>
          {(list.data?.canGrant ?? true) && (
            <Link className="adm-button" to="/sys/roles/new">
              배정 추가
            </Link>
          )}
        </div>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="배정 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            void navigate(`/sys/roles${toQueryString(Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()])))}`);
          }}
        >
          <label>
            상태
            <select name="status" defaultValue={filters.status ?? ''}>
              <option value="">전체</option>
              {Object.entries(ASSIGNMENT_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="wide">
            관리자 이름
            <input name="q" defaultValue={filters.q} maxLength={100} />
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/sys/roles">
            조건 지우기
          </Link>
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="배정 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">관리자</th>
                    <th scope="col">역할</th>
                    <th scope="col">범위</th>
                    <th scope="col">유효기간</th>
                    <th scope="col">상태</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((item) => (
                    <tr key={item.assignmentId}>
                      <td>
                        <Link to={`/sys/roles/${item.assignmentId}`}>{item.adminName}</Link>
                      </td>
                      <td>{item.roleName}</td>
                      <td>{item.scopeLabel}</td>
                      <td>
                        {item.validFrom} ~ {item.validTo ?? '제한 없음'}
                      </td>
                      <td>{ASSIGNMENT_STATUS[item.status]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 배정이 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}