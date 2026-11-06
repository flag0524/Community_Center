// 알림 이력 화면. 자동 알림과 관리자 발송 탭으로 요청별 성공·실패·확인 중 건수를 보인다 (ADM-SYS-001)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { smsListQuery } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { SMS_KIND, SMS_SCOPE } from '../../lib/labels';

const PAGE_SIZE = 20;
const KINDS = Object.keys(SMS_KIND) as Array<Schemas['SmsKind']>;

export function SmsListPage() {
  const [params] = useSearchParams();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const requested = params.get('kind') as Schemas['SmsKind'] | null;
  const kind = requested && KINDS.includes(requested) ? requested : KINDS[0]!;
  const list = useQuery(smsListQuery(kind, page));

  return (
    <>
      <div className="adm-page-heading">
        <h1>알림 이력</h1>
      </div>
      <nav className="adm-tabs" aria-label="알림 종류">
        {KINDS.map((value) => (
          <Link key={value} to={`/sys/sms?kind=${value}`} aria-current={value === kind ? 'page' : undefined}>
            {SMS_KIND[value]}
          </Link>
        ))}
      </nav>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>{SMS_KIND[kind]} 이력</h2>
          <Link className="adm-button" to="/sys/sms/new">
            문자 발송
          </Link>
        </div>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="알림 이력">
              <table>
                <thead>
                  <tr>
                    <th scope="col">요청일시</th>
                    <th scope="col">유형</th>
                    <th scope="col">문안</th>
                    <th scope="col">대상 수</th>
                    <th scope="col">성공</th>
                    <th scope="col">실패</th>
                    <th scope="col">확인중</th>
                    <th scope="col">요청자</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((item) => (
                    <tr key={item.smsId}>
                      <td>
                        <Link to={`/sys/sms/${item.smsId}`}>{kstDateTime(item.requestedAt)}</Link>
                      </td>
                      <td>
                        {SMS_KIND[item.kind]} · {SMS_SCOPE[item.scope]}
                      </td>
                      <td>{item.summary}</td>
                      <td>{item.targetCount}</td>
                      <td>{item.sent}</td>
                      <td>{item.failed}</td>
                      <td>{item.unknown}</td>
                      <td>{item.requestedBy}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>이력이 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={(next) => `/sys/sms?kind=${kind}${next > 1 ? `&page=${next}` : ''}`} />
          </>
        )}
      </section>
    </>
  );
}