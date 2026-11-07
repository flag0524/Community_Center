// 보존·파기 검토 목록 화면. 파기 예정 자료와 건수, 기준일·예정일을 보이고 정산자료가 대상에서 빠진다는 사실을 알린다 (ADM-SYS-005)
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { retentionListQuery } from '../../api/queries';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { RETENTION_STATE, RETENTION_TARGET } from '../../lib/labels';

export function RetentionListPage() {
  const list = useQuery(retentionListQuery);
  return (
    <>
      <div className="adm-page-heading">
        <h1>보존·파기 검토</h1>
      </div>
      {list.isPending && <p role="status">불러오는 중입니다.</p>}
      {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
      {list.data && (
        <>
          {list.data.exclusions.map((item) => (
            <p key={item.label} className="adm-notice">
              {item.label}는 이 목록에서 제외됩니다. {item.reason}
            </p>
          ))}
          <TableWrap label="파기 예정 목록">
            <table>
              <thead>
                <tr>
                  <th scope="col">대상 유형</th>
                  <th scope="col">건수</th>
                  <th scope="col">기준일</th>
                  <th scope="col">예정일</th>
                  <th scope="col">상태</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((item) => (
                  <tr key={item.itemId}>
                    <td>
                      <Link to={`/sys/retention/${item.itemId}`}>{RETENTION_TARGET[item.target]}</Link>
                    </td>
                    <td>{item.count.toLocaleString('ko-KR')}건</td>
                    <td>{item.baseDate ?? '-'}</td>
                    <td>{item.dueOn ?? '미정'}</td>
                    <td>{RETENTION_STATE[item.state]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          {list.data.items.length === 0 && <p>파기 예정 자료가 없습니다.</p>}
        </>
      )}
    </>
  );
}