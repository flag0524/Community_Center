// 대시보드 화면. 기수 하나의 접수 현황과 확인할 업무, 강좌별 수요, 최근 작업을 실제 집계로 보인다 (ADM-DSH-001)
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { courseOptionsQuery, dashboardQuery } from '../../api/queries';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime, won } from '../../lib/format';
import { DASHBOARD_TASK, DASHBOARD_TASK_LINK } from '../../lib/labels';

const percent = (demand: number, capacity: number) => (capacity > 0 ? `${Math.round((demand / capacity) * 100)}%` : '-');

export function DashboardPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const options = useQuery(courseOptionsQuery);
  const cycleId = params.get('cycleId') ?? options.data?.cycles[0]?.id;
  const dashboard = useQuery({ ...dashboardQuery(cycleId), enabled: !options.isPending });

  return (
    <>
      <div className="adm-page-heading">
        <h1>대시보드</h1>
      </div>
      <form className="adm-toolbar" role="search" aria-label="기수 선택" onSubmit={(event) => event.preventDefault()}>
        <label>
          교육기수
          <select value={cycleId ?? ''} onChange={(event) => void navigate(`/dashboard?cycleId=${event.target.value}`)}>
            {options.data?.cycles.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        {dashboard.data && <p className="adm-state">기준 {kstDateTime(dashboard.data.basis.basisAt)}</p>}
      </form>
      {(options.isPending || dashboard.isPending) && <p role="status">불러오는 중입니다.</p>}
      {dashboard.isError && <p role="alert">{errorMessage(dashboard.error)}</p>}
      {dashboard.data && (
        <>
          <section className="adm-panel" aria-labelledby="dash-summary">
            <div className="adm-panel-head">
              <h2 id="dash-summary">접수 현황</h2>
            </div>
            {dashboard.data.summary ? (
              <dl className="adm-kpis">
                {[
                  ['신청건', dashboard.data.summary.applications],
                  ['고유 신청자', dashboard.data.summary.uniqueApplicants],
                  ['등록완료', dashboard.data.summary.confirmed],
                  ['좌석점유', dashboard.data.summary.seatsHeld],
                  ['대기', dashboard.data.summary.waiting],
                  ['취소', dashboard.data.summary.cancelled],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{(value as number).toLocaleString('ko-KR')}</dd>
                  </div>
                ))}
                <div>
                  <dt>순수납</dt>
                  <dd>{won(dashboard.data.summary.netRevenue)}</dd>
                </div>
              </dl>
            ) : (
              <p>자료 없음. 이 기수에는 집계할 신청이 아직 없습니다.</p>
            )}
          </section>

          <section className="adm-panel" aria-labelledby="dash-tasks">
            <div className="adm-panel-head">
              <h2 id="dash-tasks">확인할 업무</h2>
            </div>
            {dashboard.data.tasks.length > 0 ? (
              <ul className="adm-list">
                {dashboard.data.tasks.map((task) => (
                  <li key={task.kind}>
                    <Link to={DASHBOARD_TASK_LINK[task.kind]}>
                      {DASHBOARD_TASK[task.kind]} {task.count}건
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p>확인할 수 있는 업무가 없습니다.</p>
            )}
          </section>

          <section className="adm-panel" aria-labelledby="dash-demand">
            <div className="adm-panel-head">
              <h2 id="dash-demand">강좌별 수요 (유효수요/정원)</h2>
            </div>
            {dashboard.data.demand.length > 0 ? (
              <TableWrap label="강좌별 수요 표">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">강좌</th>
                      <th scope="col">유효수요/정원</th>
                      <th scope="col">비율</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.data.demand.map((row) => (
                      <tr key={row.courseId}>
                        <td>{row.courseName}</td>
                        <td>
                          {row.effectiveDemand}/{row.capacity}
                        </td>
                        <td>{percent(row.effectiveDemand, row.capacity)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            ) : (
              <p>자료 없음.</p>
            )}
          </section>

          <section className="adm-panel" aria-labelledby="dash-recent">
            <div className="adm-panel-head">
              <h2 id="dash-recent">최근 작업</h2>
            </div>
            {dashboard.data.recent.length > 0 ? (
              <TableWrap label="최근 작업 표">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">시각</th>
                      <th scope="col">처리자</th>
                      <th scope="col">작업</th>
                      <th scope="col">대상</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.data.recent.map((entry) => (
                      <tr key={`${entry.at}-${entry.action}`}>
                        <td>{kstDateTime(entry.at)}</td>
                        <td>{entry.actor}</td>
                        <td>{entry.action}</td>
                        <td>{entry.target}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            ) : (
              <p>최근 작업이 없습니다.</p>
            )}
          </section>
        </>
      )}
    </>
  );
}