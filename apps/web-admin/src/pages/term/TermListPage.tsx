// 약관·동의문 버전 목록 화면. 문안 종류 탭마다 버전을 시행일 순으로 보이고 새 버전은 이전 버전을 복제해 시작한다 (ADM-MBR-005)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { termVersionListQuery } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { TERM_STATUS, TERM_TYPE } from '../../lib/labels';

const PAGE_SIZE = 20;
const TYPES = Object.keys(TERM_TYPE) as Array<Schemas['TermType']>;

export function TermListPage() {
  const [params] = useSearchParams();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const requested = params.get('type') as Schemas['TermType'] | null;
  const type = requested && TYPES.includes(requested) ? requested : TYPES[0]!;
  const list = useQuery(termVersionListQuery(type, page));
  const latest = list.data?.items[0];

  return (
    <>
      <div className="adm-page-heading">
        <h1>약관·동의문</h1>
      </div>
      <nav className="adm-tabs" aria-label="문안 종류">
        {TYPES.map((value) => (
          <Link key={value} to={`/mbr/terms?type=${value}`} aria-current={value === type ? 'page' : undefined}>
            {TERM_TYPE[value]}
          </Link>
        ))}
      </nav>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>{TERM_TYPE[type]} 버전</h2>
          <Link className="adm-button" to={`/mbr/terms/new?type=${type}${latest ? `&base=${latest.versionId}` : ''}`}>
            새 버전 작성
          </Link>
        </div>
        <p className="adm-notice">새 버전은 시행일 이후 신규 가입·재동의 시점에 적용됩니다. 이미 동의한 회원에게 다시 동의를 받는 절차는 이 화면에 없습니다.</p>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="버전 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">버전</th>
                    <th scope="col">시행일</th>
                    <th scope="col">필수</th>
                    <th scope="col">상태</th>
                    <th scope="col">게시일</th>
                    <th scope="col">동의 회원 수</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((term) => (
                    <tr key={term.versionId}>
                      <td>
                        <Link to={`/mbr/terms/${term.versionId}`}>{term.versionName}</Link>
                      </td>
                      <td>{term.effectiveOn}</td>
                      <td>{term.essential ? '필수' : '선택'}</td>
                      <td>{TERM_STATUS[term.status]}</td>
                      <td>{term.postedOn ?? '-'}</td>
                      <td>{term.agreedCount.toLocaleString('ko-KR')}명</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>등록된 버전이 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={(next) => `/mbr/terms?type=${type}${next > 1 ? `&page=${next}` : ''}`} />
          </>
        )}
      </section>
    </>
  );
}