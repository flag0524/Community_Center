// 결제·거래 대조 목록 화면. 결과 확인 중인 거래를 먼저 보이고 충돌 통보 건은 별도 탭으로 모은다 (ADM-PAY-003)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { transactionListQuery, type TransactionParams } from '../../api/queries';
import { CsvButton } from '../../components/CsvButton';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime, won } from '../../lib/format';
import { PAYMENT_METHOD, PAYMENT_STATUS } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['q', 'status', 'method', 'from', 'to'] as const;

export function TransactionListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const conflictTab = params.get('tab') === 'conflict';
  const filters: TransactionParams = {
    q: params.get('q') ?? undefined,
    status: (params.get('status') as Schemas['PaymentStatus'] | null) ?? undefined,
    method: (params.get('method') as Schemas['PaymentMethod'] | null) ?? undefined,
    from: params.get('from') ?? undefined,
    to: params.get('to') ?? undefined,
    conflictOnly: conflictTab ? 'true' : undefined,
    page,
  };
  const list = useQuery(transactionListQuery(filters));
  const tabQuery = conflictTab ? { tab: 'conflict' } : {};

  const hrefFor = (next: number) =>
    `/pay/transactions${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), ...tabQuery, page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>결제·거래 대조</h1>
      </div>
      <nav className="adm-tabs" aria-label="거래 구분">
        <Link to="/pay/transactions" aria-current={conflictTab ? undefined : 'page'}>
          전체 거래
        </Link>
        <Link to="/pay/transactions?tab=conflict" aria-current={conflictTab ? 'page' : undefined}>
          충돌 통보 건
        </Link>
      </nav>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>{conflictTab ? '충돌 통보 건' : '거래 목록'}</h2>
        </div>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="거래 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const next = Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()]));
            void navigate(`/pay/transactions${toQueryString({ ...next, ...tabQuery })}`);
          }}
        >
          <label className="wide">
            검색어
            <input name="q" defaultValue={filters.q} placeholder="주문번호 또는 신청번호" maxLength={100} />
          </label>
          <label>
            결제 상태
            <select name="status" defaultValue={filters.status ?? ''}>
              <option value="">전체</option>
              {Object.entries(PAYMENT_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            결제수단
            <select name="method" defaultValue={filters.method ?? ''}>
              <option value="">전체</option>
              {Object.entries(PAYMENT_METHOD).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            요청일 시작
            <input name="from" type="date" defaultValue={filters.from} />
          </label>
          <label>
            요청일 끝
            <input name="to" type="date" defaultValue={filters.to} />
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to={conflictTab ? '/pay/transactions?tab=conflict' : '/pay/transactions'}>
            조건 지우기
          </Link>
          <CsvButton path="/transactions/export.csv" query={toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), conflictOnly: filters.conflictOnly })} />
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="거래 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">주문번호</th>
                    <th scope="col">신청번호</th>
                    <th scope="col">금액</th>
                    <th scope="col">수단</th>
                    <th scope="col">상태</th>
                    <th scope="col">요청시각</th>
                    <th scope="col">PG 승인시각</th>
                    <th scope="col">재조회 횟수</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((row) => (
                    <tr key={row.transactionId}>
                      <td>
                        <Link to={`/pay/transactions/${row.transactionId}`}>{row.orderNo}</Link>
                      </td>
                      <td>{row.applicationNo}</td>
                      <td>{won(row.amount)}</td>
                      <td>{PAYMENT_METHOD[row.method]}</td>
                      <td>{PAYMENT_STATUS[row.status]}</td>
                      <td>{kstDateTime(row.requestedAt)}</td>
                      <td>{row.approvedAt ? kstDateTime(row.approvedAt) : '-'}</td>
                      <td>{row.recheckCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 거래가 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}
