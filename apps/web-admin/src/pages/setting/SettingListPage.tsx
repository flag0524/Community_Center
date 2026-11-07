// 운영 설정 화면. 운영 기준과 검토 상태를 읽기만 하며 확정이 실제 기능 적용 완료를 뜻하지는 않는다 (ADM-SYS-004)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { settingListQuery, type SettingParams } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { OPER_RULE_STATUS } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['status', 'q'] as const;

export function SettingListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: SettingParams = { status: (params.get('status') as Schemas['OperRuleStatus'] | null) ?? undefined, q: params.get('q') ?? undefined, page };
  const list = useQuery(settingListQuery(filters));
  const hrefFor = (next: number) => `/sys/settings${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>운영 설정</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>운영 기준</h2>
        </div>
        <p className="adm-notice">읽기 전용입니다. 확정은 기준이 정해졌다는 뜻이며 실제 기능에 적용이 끝났다는 뜻은 아닙니다. 기준이 바뀌면 새 버전과 작업 이력이 남습니다.</p>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="운영 설정 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            void navigate(`/sys/settings${toQueryString(Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()])))}`);
          }}
        >
          <label>
            상태
            <select name="status" defaultValue={filters.status ?? ''}>
              <option value="">전체</option>
              {Object.entries(OPER_RULE_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="wide">
            항목명
            <input name="q" defaultValue={filters.q} maxLength={100} />
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/sys/settings">
            조건 지우기
          </Link>
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="운영 기준 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">항목</th>
                    <th scope="col">현재 기준</th>
                    <th scope="col">상태</th>
                    <th scope="col">수정일</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((item) => (
                    <tr key={item.settingId}>
                      <td>
                        <Link to={`/sys/settings/${item.settingId}`}>{item.name}</Link>
                      </td>
                      <td>{item.value}</td>
                      <td>{OPER_RULE_STATUS[item.status]}</td>
                      <td>{item.updatedOn}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 항목이 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}