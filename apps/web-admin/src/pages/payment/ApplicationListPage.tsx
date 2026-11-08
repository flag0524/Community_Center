// 수강신청 관리 목록 화면. 조회 전용이며 신청자 이름은 가려서 보인다 (ADM-PAY-001)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { adminApplicationListQuery, courseOptionsQuery, type AdminApplicationParams } from '../../api/queries';
import { CsvButton } from '../../components/CsvButton';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { APPLICATION_STATUS, DISPLAY_STATE, PAYMENT_STATUS, REFUND_STATUS } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['q', 'cycleId', 'courseId', 'status', 'paymentStatus', 'from', 'to'] as const;

export function ApplicationListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: AdminApplicationParams = {
    q: params.get('q') ?? undefined,
    cycleId: params.get('cycleId') ?? undefined,
    courseId: params.get('courseId') ?? undefined,
    status: (params.get('status') as Schemas['ApplicationStatus'] | null) ?? undefined,
    paymentStatus: (params.get('paymentStatus') as Schemas['PaymentStatus'] | null) ?? undefined,
    from: params.get('from') ?? undefined,
    to: params.get('to') ?? undefined,
    page,
  };
  const list = useQuery(adminApplicationListQuery(filters));
  const options = useQuery(courseOptionsQuery);

  const hrefFor = (next: number) =>
    `/pay/applications${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>수강신청</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>수강신청 목록</h2>
        </div>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="수강신청 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const next = Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()]));
            void navigate(`/pay/applications${toQueryString(next)}`);
          }}
        >
          <label className="wide">
            검색어
            <input name="q" defaultValue={filters.q} placeholder="신청번호 또는 이름" maxLength={100} />
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
            신청 상태
            <select name="status" defaultValue={filters.status ?? ''}>
              <option value="">전체</option>
              {Object.entries(APPLICATION_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            결제 상태
            <select name="paymentStatus" defaultValue={filters.paymentStatus ?? ''}>
              <option value="">전체</option>
              {Object.entries(PAYMENT_STATUS).map(([value, label]) => (
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
          <Link className="adm-button secondary" to="/pay/applications">
            조건 지우기
          </Link>
          <CsvButton path="/applications/export.csv" query={toQueryString(Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])))} />
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="수강신청 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">신청번호</th>
                    <th scope="col">강좌</th>
                    <th scope="col">신청자</th>
                    <th scope="col">신청상태</th>
                    <th scope="col">결제상태</th>
                    <th scope="col">환불상태</th>
                    <th scope="col">접수시각</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((row) => (
                    <tr key={row.applicationId}>
                      <td>
                        <Link to={`/pay/applications/${row.applicationId}`}>{row.applicationNo}</Link>
                      </td>
                      <td>{row.courseName}</td>
                      <td>{row.applicantName}</td>
                      <td>{DISPLAY_STATE[row.displayState]}</td>
                      <td>{row.paymentStatus ? PAYMENT_STATUS[row.paymentStatus] : '-'}</td>
                      <td>{row.refundStatus ? REFUND_STATUS[row.refundStatus] : '-'}</td>
                      <td>{kstDateTime(row.appliedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 신청이 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}
