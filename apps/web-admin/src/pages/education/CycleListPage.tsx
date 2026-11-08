// 교육기수 목록 화면. 연도·차수·기간·연결 강좌 수를 보여 준다 (ADM-EDU-002)
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { cycleListQuery } from '../../api/queries';
import { CsvButton } from '../../components/CsvButton';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { CYCLE_STATUS } from '../../lib/labels';

const PAGE_SIZE = 20;

export function CycleListPage() {
  const [params] = useSearchParams();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const { data, isPending, isError, error } = useQuery(cycleListQuery(page));

  return (
    <>
      <div className="adm-page-heading">
        <h1>교육기수</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>교육기수 목록</h2>
          <Link className="adm-button" to="/edu/cycles/new">
            등록
          </Link>
          <CsvButton path="/cycles/export.csv" query="" />
        </div>
        {isPending && <p role="status">불러오는 중입니다.</p>}
        {isError && <p role="alert">{errorMessage(error)}</p>}
        {data && (
          <>
            <ResultCount total={data.total} />
            <TableWrap label="교육기수 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">연도</th>
                    <th scope="col">차수</th>
                    <th scope="col">기수명</th>
                    <th scope="col">모집기간</th>
                    <th scope="col">교육기간</th>
                    <th scope="col">연결 강좌 수</th>
                    <th scope="col">상태</th>
                    <th scope="col">관리</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((cycle) => (
                    <tr key={cycle.cycleId}>
                      <td>{cycle.year}</td>
                      <td>{cycle.order}</td>
                      <td>
                        <Link to={`/edu/cycles/${cycle.cycleId}`}>{cycle.name}</Link>
                      </td>
                      <td>
                        {cycle.receptionStart} ~ {cycle.receptionEnd}
                      </td>
                      <td>
                        {cycle.educationStart} ~ {cycle.educationEnd}
                      </td>
                      <td>{cycle.courseCount}</td>
                      <td>{CYCLE_STATUS[cycle.status]}</td>
                      <td>
                        <Link className="adm-button secondary" to={`/edu/cycles/${cycle.cycleId}`} aria-label={`수정 (${cycle.name})`}>
                          수정
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            <AdminPager page={page} total={data.total} size={PAGE_SIZE} hrefFor={(next) => `/edu/cycles?page=${next}`} />
          </>
        )}
      </section>
    </>
  );
}
