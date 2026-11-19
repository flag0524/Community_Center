// 강좌 만족도 집계자료 목록 화면. 기관이 준 조사 결과의 강좌·버전·조사 기간·승인 상태를 보이고 등록 담당자에게 등록 버튼을 보인다 (ADM-DSH-002 집계자료)
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { satisfactionSourceListQuery } from '../../api/queries';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { STATS_SOURCE_STATE } from '../../lib/labels';
import { useHasAuthority } from '../../layout/menu';

export function SatisfactionListPage() {
  const list = useQuery(satisfactionSourceListQuery);
  const canRegister = useHasAuthority('AU.CONF_W');
  return (
    <>
      <div className="adm-page-heading">
        <h1>강좌 만족도 집계자료</h1>
        {canRegister && (
          <Link className="adm-button" to="/satisfaction-sources/new">
            집계자료 등록
          </Link>
        )}
      </div>
      <p className="adm-notice">기관이 제공한 집계 결과만 등록합니다. 개인 응답은 받지 않습니다. 승인한 자료 중 가장 나중에 승인한 한 버전만 만족도 통계에 쓰이며 버전을 합산하지 않습니다. 승인한 자료는 고칠 수 없고 새 버전으로 등록합니다.</p>
      {list.isPending && <p role="status">불러오는 중입니다.</p>}
      {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
      {list.data && (
        <>
          <TableWrap label="만족도 집계자료 목록">
            <table>
              <thead>
                <tr>
                  <th scope="col">강좌</th>
                  <th scope="col">계열</th>
                  <th scope="col">버전</th>
                  <th scope="col">출처</th>
                  <th scope="col">조사 기간</th>
                  <th scope="col">응답자</th>
                  <th scope="col">상태</th>
                  <th scope="col">등록일시</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((item) => (
                  <tr key={item.sourceId}>
                    <td>
                      <Link to={`/satisfaction-sources/${item.sourceId}`}>{item.courseName}</Link>
                    </td>
                    <td>{item.datasetId}</td>
                    <td>{item.version}</td>
                    <td>{item.provider}</td>
                    <td>{item.periodStart ?? '-'} ~ {item.periodEnd ?? '-'}</td>
                    <td>{item.respondents.toLocaleString('ko-KR')}명</td>
                    <td>{STATS_SOURCE_STATE[item.state]}</td>
                    <td>{kstDateTime(item.registeredAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          {list.data.items.length === 0 && <p>등록한 집계자료가 없습니다.</p>}
        </>
      )}
    </>
  );
}
