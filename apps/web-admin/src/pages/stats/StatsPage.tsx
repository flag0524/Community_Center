// 통계 화면. 수요·정산·출석·만족도·연령 성별 탭이 같은 조건 영역을 쓰고 자료가 없는 것과 0을 구분해 보인다 (ADM-DSH-002)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ageGenderStatsQuery, attendanceStatsQuery, courseOptionsQuery, demandStatsQuery, satisfactionStatsQuery, settlementStatsQuery, type StatsParams } from '../../api/queries';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime, won } from '../../lib/format';
import { PAYMENT_METHOD } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const TABS = [
  { key: 'demand', label: '수요' },
  { key: 'settlement', label: '정산' },
  { key: 'attendance', label: '출석' },
  { key: 'satisfaction', label: '만족도' },
  { key: 'age', label: '연령·성별' },
] as const;
type Tab = (typeof TABS)[number]['key'];
const FILTERS = ['cycleId', 'from', 'to', 'categoryId'] as const;
const percent = (value: number | null | undefined) => (value == null ? '-' : `${Math.round(value * 100)}%`);

export function StatsPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const requested = params.get('tab');
  const tab: Tab = TABS.some((item) => item.key === requested) ? (requested as Tab) : 'demand';
  const filtered = tab === 'demand' || tab === 'settlement' || tab === 'attendance';
  const filters: StatsParams = {
    cycleId: params.get('cycleId') ?? undefined,
    from: params.get('from') ?? undefined,
    to: params.get('to') ?? undefined,
    categoryId: tab === 'demand' ? (params.get('categoryId') ?? undefined) : undefined,
  };
  const options = useQuery(courseOptionsQuery);

  return (
    <>
      <div className="adm-page-heading">
        <h1>수요·연령·정산 통계</h1>
      </div>
      <nav className="adm-tabs" aria-label="통계 종류">
        {TABS.map((item) => (
          <Link key={item.key} to={`/stats?tab=${item.key}`} aria-current={item.key === tab ? 'page' : undefined}>
            {item.label}
          </Link>
        ))}
      </nav>
      {filtered && (
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="통계 조건"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            void navigate(`/stats${toQueryString({ tab, ...Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()])) })}`);
          }}
        >
          <label>
            교육기수
            <select name="cycleId" defaultValue={filters.cycleId ?? ''}>
              <option value="">전체 기수</option>
              {options.data?.cycles.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          {tab === 'demand' && (
            <label>
              분야
              <select name="categoryId" defaultValue={filters.categoryId ?? ''}>
                <option value="">전체 분야</option>
                {options.data?.classes.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
          )}
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
          <Link className="adm-button secondary" to={`/stats?tab=${tab}`}>
            조건 지우기
          </Link>
        </form>
      )}
      {tab === 'demand' && <DemandTab filters={filters} />}
      {tab === 'settlement' && <SettlementTab filters={filters} />}
      {tab === 'attendance' && <AttendanceTab filters={filters} />}
      {tab === 'satisfaction' && <SatisfactionTab />}
      {tab === 'age' && <AgeTab />}
    </>
  );
}

function Basis({ basis }: { basis: Schemas['StatsBasis'] }) {
  return <p className="adm-state">집계 기준 {kstDateTime(basis.basisAt)}</p>;
}

function Loading({ query }: { query: { isPending: boolean; isError: boolean; error: unknown } }) {
  if (query.isPending) return <p role="status">불러오는 중입니다.</p>;
  if (query.isError) return <p role="alert">{errorMessage(query.error)}</p>;
  return null;
}

function DemandTab({ filters }: { filters: StatsParams }) {
  const query = useQuery(demandStatsQuery(filters));
  return (
    <section className="adm-panel" aria-label="수요 탭">
      <Loading query={query} />
      {query.data && (
        <>
          <Basis basis={query.data.basis} />
          <p className="adm-notice">좌석점유는 등록완료·결제대기·승인확인중을 더한 값이고, 유효수요는 좌석점유에 대기를 더한 값입니다. 표 내려받기는 첨부 설계 뒤에 더합니다.</p>
          {query.data.rows.length > 0 ? (
            <TableWrap label="수요 통계">
              <table>
                <thead>
                  <tr>
                    <th scope="col">강좌</th>
                    <th scope="col">분야</th>
                    <th scope="col">정원</th>
                    <th scope="col">신청건</th>
                    <th scope="col">고유 신청자</th>
                    <th scope="col">등록완료</th>
                    <th scope="col">결제대기</th>
                    <th scope="col">승인확인중</th>
                    <th scope="col">대기</th>
                    <th scope="col">취소</th>
                    <th scope="col">좌석점유</th>
                    <th scope="col">유효수요</th>
                    <th scope="col">유효수요/정원</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.rows.map((row) => (
                    <tr key={row.courseId}>
                      <td>{row.courseName}</td>
                      <td>{row.categoryName}</td>
                      <td>{row.capacity}</td>
                      <td>{row.applications}</td>
                      <td>{row.uniqueApplicants}</td>
                      <td>{row.confirmed}</td>
                      <td>{row.hold}</td>
                      <td>{row.paymentUnknown}</td>
                      <td>{row.waiting}</td>
                      <td>{row.cancelled}</td>
                      <td>{row.seatsHeld}</td>
                      <td>{row.effectiveDemand}</td>
                      <td>{percent(row.demandRatio)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          ) : (
            <p>자료 없음. 조건에 맞는 신청이 없습니다.</p>
          )}
        </>
      )}
    </section>
  );
}

function SettlementTab({ filters }: { filters: StatsParams }) {
  const query = useQuery(settlementStatsQuery(filters));
  const data = query.data;
  return (
    <section className="adm-panel" aria-label="정산 탭">
      <Loading query={query} />
      {data && (
        <>
          <Basis basis={data.basis} />
          {data.byMethod.length > 0 ? (
            <>
              <dl className="adm-facts">
                <dt>승인금액</dt>
                <dd>{won(data.approvedAmount)}</dd>
                <dt>완료환불액</dt>
                <dd>{won(data.refundedAmount)}</dd>
                <dt>순수납</dt>
                <dd>{won(data.netRevenue)}</dd>
                <dt>확인 중 금액</dt>
                <dd>{won(data.unknownAmount)} (순수납에 넣지 않았습니다)</dd>
              </dl>
              <TableWrap label="결제수단별 정산">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">결제수단</th>
                      <th scope="col">승인금액</th>
                      <th scope="col">완료환불액</th>
                      <th scope="col">순수납</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.byMethod.map((row) => (
                      <tr key={row.method}>
                        <td>{PAYMENT_METHOD[row.method]}</td>
                        <td>{won(row.approved)}</td>
                        <td>{won(row.refunded)}</td>
                        <td>{won(row.net)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            </>
          ) : (
            <p>자료 없음. 조건에 맞는 결제가 없습니다.</p>
          )}
        </>
      )}
    </section>
  );
}

function AttendanceTab({ filters }: { filters: StatsParams }) {
  const query = useQuery(attendanceStatsQuery(filters));
  return (
    <section className="adm-panel" aria-label="출석 탭">
      <Loading query={query} />
      {query.data && (
        <>
          <Basis basis={query.data.basis} />
          <p className="adm-notice">출석률은 출석 ÷ (출석 + 결석)이며 체크하지 않은 회차는 제외합니다. 출석 통계는 내려받을 수 없습니다.</p>
          {query.data.rows.length > 0 ? (
            <TableWrap label="출석 통계">
              <table>
                <thead>
                  <tr>
                    <th scope="col">강좌</th>
                    <th scope="col">강사</th>
                    <th scope="col">출석</th>
                    <th scope="col">결석</th>
                    <th scope="col">출석률</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.rows.map((row) => (
                    <tr key={row.courseId}>
                      <td>{row.courseName}</td>
                      <td>{row.instructorName}</td>
                      <td>{row.present}</td>
                      <td>{row.absent}</td>
                      <td>{row.rate == null ? '체크 없음' : `${row.rate}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          ) : (
            <p>자료 없음. 조건에 맞는 출석이 없습니다.</p>
          )}
        </>
      )}
    </section>
  );
}

function SourceFacts({ source }: { source: Schemas['StatsSource'] }) {
  return (
    <dl className="adm-facts">
      <dt>자료 버전</dt>
      <dd>{source.version}</dd>
      <dt>제공 기관</dt>
      <dd>{source.provider}</dd>
      <dt>조사·집계 기간</dt>
      <dd>{source.period}</dd>
      {source.basisDate && (
        <>
          <dt>기준일</dt>
          <dd>{source.basisDate}</dd>
        </>
      )}
    </dl>
  );
}

function SatisfactionTab() {
  const query = useQuery(satisfactionStatsQuery);
  const data = query.data;
  return (
    <section className="adm-panel" aria-label="만족도 탭">
      <Loading query={query} />
      {data &&
        (data.source ? (
          <>
            <Basis basis={data.basis} />
            <SourceFacts source={data.source} />
            <p>응답자 {data.respondents?.toLocaleString('ko-KR') ?? '-'}명 · 기관이 제공한 승인 자료만 보이며 내려받기는 없습니다.</p>
            <TableWrap label="만족도 통계">
              <table>
                <thead>
                  <tr>
                    <th scope="col">문항</th>
                    <th scope="col">응답</th>
                    <th scope="col">평균</th>
                    <th scope="col">분포</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr key={item.question}>
                      <td>{item.question}</td>
                      <td>{item.answered}건</td>
                      <td>{item.average == null ? '산출 안 함' : item.average.toFixed(1)}</td>
                      <td>{item.options.length > 0 ? item.options.map((option) => `${option.label} ${option.count}`).join(' · ') : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </>
        ) : (
          <p>미제공. 기관이 제공해 승인한 만족도 자료가 아직 없습니다.</p>
        ))}
    </section>
  );
}

function AgeTab() {
  const query = useQuery(ageGenderStatsQuery);
  const data = query.data;
  return (
    <section className="adm-panel" aria-label="연령·성별 탭">
      <Loading query={query} />
      {data &&
        (data.source ? (
          <>
            <Basis basis={data.basis} />
            <SourceFacts source={data.source} />
            <p className="adm-notice">회원 개인 항목이 아니라 기관이 제공해 승인한 집계자료를 그대로 보입니다. 다른 버전은 합산하지 않습니다.</p>
            <TableWrap label="연령·성별 통계">
              <table>
                <thead>
                  <tr>
                    <th scope="col">연령 구간</th>
                    <th scope="col">남</th>
                    <th scope="col">여</th>
                    <th scope="col">미상</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.band}>
                      <td>{row.band}</td>
                      <td>{row.male}명</td>
                      <td>{row.female}명</td>
                      <td>{row.unknown}명</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </>
        ) : (
          <p>미제공. 기관이 제공해 승인한 집계자료가 아직 없습니다.</p>
        ))}
    </section>
  );
}