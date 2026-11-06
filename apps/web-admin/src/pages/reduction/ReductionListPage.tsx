// 감면 검토 목록 화면. 접수된 사전심사가 오래된 신청부터 먼저 나오고 상태·기수로 좁힌다 (ADM-PAY-005)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { courseOptionsQuery, reductionListQuery, type ReductionParams } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { REDUCTION_STATUS, REDUCTION_TYPE } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['status', 'cycleId'] as const;

export function ReductionListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: ReductionParams = { status: (params.get('status') as Schemas['ReductionStatus'] | null) ?? undefined, cycleId: params.get('cycleId') ?? undefined, page };
  const list = useQuery(reductionListQuery(filters));
  const options = useQuery(courseOptionsQuery);
  const hrefFor = (next: number) => `/pay/reductions${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>감면 검토</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>사전 심사 신청</h2>
          <Link className="adm-button secondary" to="/pay/reduction-history">
            처리 이력
          </Link>
        </div>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="감면 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            void navigate(`/pay/reductions${toQueryString(Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()])))}`);
          }}
        >
          <label>
            상태
            <select name="status" defaultValue={filters.status ?? ''}>
              <option value="">전체</option>
              {Object.entries(REDUCTION_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            교육기수
            <select name="cycleId" defaultValue={filters.cycleId ?? ''}>
              <option value="">전체 기수</option>
              {options.data?.cycles.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/pay/reductions">
            조건 지우기
          </Link>
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="감면 심사 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">회원</th>
                    <th scope="col">기수</th>
                    <th scope="col">감면 유형</th>
                    <th scope="col">증빙 수</th>
                    <th scope="col">신청일</th>
                    <th scope="col">상태</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((item) => (
                    <tr key={item.reviewId}>
                      <td>
                        <Link to={`/pay/reductions/${item.reviewId}`}>{item.memberName}</Link>
                      </td>
                      <td>{item.cycleName}</td>
                      <td>{REDUCTION_TYPE[item.reductionType]}</td>
                      <td>{item.evidenceCount}</td>
                      <td>{item.appliedOn}</td>
                      <td>{REDUCTION_STATUS[item.status]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 심사가 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}