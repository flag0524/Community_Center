// 감면 처리 이력 화면. 신청에 적용된 판정이 새 행으로 쌓인 기록을 조회만 한다 (ADM-PAY-006)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { reductionHistoryQuery, type ReductionHistoryParams } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime, won } from '../../lib/format';
import { REDUCTION_DECISION } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['result', 'from', 'to'] as const;

export function ReductionHistoryPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: ReductionHistoryParams = { result: (params.get('result') as Schemas['ReductionDecision'] | null) ?? undefined, from: params.get('from') ?? undefined, to: params.get('to') ?? undefined, page };
  const list = useQuery(reductionHistoryQuery(filters));
  const hrefFor = (next: number) => `/pay/reduction-history${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>감면 처리 이력</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>판정 이력</h2>
        </div>
        <p className="adm-notice">판정마다 새 행으로 쌓이며 고치거나 지울 수 없습니다. 취소·환불로 감면권이 자동으로 되살아나지 않습니다.</p>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="이력 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            void navigate(`/pay/reduction-history${toQueryString(Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()])))}`);
          }}
        >
          <label>
            결과
            <select name="result" defaultValue={filters.result ?? ''}>
              <option value="">전체</option>
              {Object.entries(REDUCTION_DECISION).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            시작일
            <input name="from" type="date" defaultValue={filters.from} />
          </label>
          <label>
            종료일
            <input name="to" type="date" defaultValue={filters.to} />
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/pay/reduction-history">
            조건 지우기
          </Link>
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="감면 처리 이력">
              <table>
                <thead>
                  <tr>
                    <th scope="col">판정일시</th>
                    <th scope="col">회원</th>
                    <th scope="col">기수</th>
                    <th scope="col">결과</th>
                    <th scope="col">감면액</th>
                    <th scope="col">사유</th>
                    <th scope="col">처리자</th>
                    <th scope="col">증빙</th>
                    <th scope="col">사용 신청</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((row) => (
                    <tr key={row.historyId}>
                      <td>{kstDateTime(row.decidedAt)}</td>
                      <td>{row.memberName}</td>
                      <td>{row.cycleName}</td>
                      <td>{REDUCTION_DECISION[row.result]}</td>
                      <td>{row.amount == null ? '-' : won(row.amount)}</td>
                      <td>{row.reason ?? '-'}</td>
                      <td>{row.decidedBy}</td>
                      <td>{row.evidenceCount}건</td>
                      <td>{row.applicationNo ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 이력이 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}