// 환불 검토 목록 화면. 접수·보류 건을 오래된 것부터 먼저 보이고 심사 목표 3영업일을 넘긴 건은 글자로 알린다 (ADM-PAY-004)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { adminRefundListQuery, type AdminRefundParams } from '../../api/queries';
import { CsvButton } from '../../components/CsvButton';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { won } from '../../lib/format';
import { REFUND_REQUESTER, REFUND_STATUS } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['status', 'requester', 'from', 'to'] as const;

export function RefundListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: AdminRefundParams = {
    status: (params.get('status') as Schemas['RefundStatus'] | null) ?? undefined,
    requester: (params.get('requester') as Schemas['RefundRequester'] | null) ?? undefined,
    from: params.get('from') ?? undefined,
    to: params.get('to') ?? undefined,
    page,
  };
  const list = useQuery(adminRefundListQuery(filters));

  const hrefFor = (next: number) =>
    `/pay/refunds${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>환불 검토</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>환불 목록</h2>
          <Link className="adm-button" to="/pay/refunds/new">
            방문·유선 환불 접수
          </Link>
        </div>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="환불 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const next = Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()]));
            void navigate(`/pay/refunds${toQueryString(next)}`);
          }}
        >
          <label>
            환불 상태
            <select name="status" defaultValue={filters.status ?? ''}>
              <option value="">전체</option>
              {Object.entries(REFUND_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            요청 주체
            <select name="requester" defaultValue={filters.requester ?? ''}>
              <option value="">전체</option>
              {Object.entries(REFUND_REQUESTER).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            접수일 시작
            <input name="from" type="date" defaultValue={filters.from} />
          </label>
          <label>
            접수일 끝
            <input name="to" type="date" defaultValue={filters.to} />
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/pay/refunds">
            조건 지우기
          </Link>
          <CsvButton path="/refunds/export.csv" query={toQueryString(Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])))} />
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="환불 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">환불번호</th>
                    <th scope="col">신청번호</th>
                    <th scope="col">강좌</th>
                    <th scope="col">요청액</th>
                    <th scope="col">상태</th>
                    <th scope="col">접수일</th>
                    <th scope="col">경과 영업일</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((row) => (
                    <tr key={row.refundId}>
                      <td>
                        <Link to={`/pay/refunds/${row.refundId}`}>{row.refundNo}</Link>
                      </td>
                      <td>{row.applicationNo}</td>
                      <td>{row.courseName}</td>
                      <td>{won(row.requestedAmount)}</td>
                      <td>{REFUND_STATUS[row.status]}</td>
                      <td>{row.receivedOn}</td>
                      <td>
                        {row.elapsedBusinessDays}일{row.overdue && <strong className="adm-overdue"> · 3영업일 초과</strong>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 환불이 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}
