// 회원 관리 목록 화면. 이름은 가려서 보이고 연령대는 보이지 않는다(개인 연령은 집계자료로만 다룬다) (ADM-MBR-001)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { memberListQuery, type MemberParams } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { PiiExportButton } from '../../components/PiiExportButton';
import { errorMessage } from '../../lib/errors';
import { MEMBER_STATUS, RESIDENCE_DECLARED, RESIDENCE_STATUS } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['q', 'status'] as const;

export function MemberListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: MemberParams = {
    q: params.get('q') ?? undefined,
    status: (params.get('status') as Schemas['MemberStatus'] | null) ?? undefined,
    page,
  };
  const list = useQuery(memberListQuery(filters));

  const hrefFor = (next: number) =>
    `/mbr/members${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>회원 관리</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>회원 목록</h2>
        </div>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="회원 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const next = Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()]));
            void navigate(`/mbr/members${toQueryString(next)}`);
          }}
        >
          <label className="wide">
            검색어
            <input name="q" defaultValue={filters.q} placeholder="아이디 또는 이름" maxLength={100} />
          </label>
          <label>
            이용 상태
            <select name="status" defaultValue={filters.status ?? ''}>
              <option value="">전체</option>
              {Object.entries(MEMBER_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/mbr/members">
            조건 지우기
          </Link>
          <PiiExportButton label="암호화 파일 요청" body={{ target: 'MEMBERS', q: filters.q, status: filters.status }} />
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="회원 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">회원 ID</th>
                    <th scope="col">이름</th>
                    <th scope="col">거주범위</th>
                    <th scope="col">가입일</th>
                    <th scope="col">이용상태</th>
                    <th scope="col">관리</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((member) => (
                    <tr key={member.memberId}>
                      <td>
                        <Link to={`/mbr/members/${member.memberId}`}>{member.loginId}</Link>
                      </td>
                      <td>{member.nameMasked}</td>
                      <td>
                        {member.residenceDeclared ? `${RESIDENCE_DECLARED[member.residenceDeclared]} (${RESIDENCE_STATUS[member.residenceStatus]})` : '-'}
                      </td>
                      <td>{member.joinedOn}</td>
                      <td>{MEMBER_STATUS[member.status]}</td>
                      <td>
                        <Link className="adm-button secondary" to={`/mbr/members/${member.memberId}`} aria-label={`조회 (${member.loginId})`}>
                          조회
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 회원이 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}
