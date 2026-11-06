// 홈·센터 콘텐츠 목록 화면. 유형 탭을 고르면 그 유형의 콘텐츠를 정렬 순서대로 보인다 (ADM-MBR-004)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { adminContentListQuery } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { CONTENT_TYPE } from '../../lib/labels';

const PAGE_SIZE = 20;
const TYPES = Object.keys(CONTENT_TYPE) as Array<Schemas['ContentType']>;

export function ContentListPage() {
  const [params] = useSearchParams();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const requested = params.get('type') as Schemas['ContentType'] | null;
  const type = requested && TYPES.includes(requested) ? requested : TYPES[0]!;
  const list = useQuery(adminContentListQuery({ type, page }));

  return (
    <>
      <div className="adm-page-heading">
        <h1>홈·센터 콘텐츠</h1>
      </div>
      <nav className="adm-tabs" aria-label="콘텐츠 유형">
        {TYPES.map((value) => (
          <Link key={value} to={`/mbr/contents?type=${value}`} aria-current={value === type ? 'page' : undefined}>
            {CONTENT_TYPE[value]}
          </Link>
        ))}
      </nav>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>{CONTENT_TYPE[type]} 목록</h2>
          {(list.data?.canCreate ?? true) && (
            <Link className="adm-button" to={`/mbr/contents/new?type=${type}`}>
              등록
            </Link>
          )}
        </div>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="콘텐츠 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">제목</th>
                    <th scope="col">게시</th>
                    <th scope="col">게시 기간</th>
                    <th scope="col">정렬</th>
                    <th scope="col">수정일</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((content) => (
                    <tr key={content.contentId}>
                      <td>
                        <Link to={`/mbr/contents/${content.contentId}`}>{content.title}</Link>
                      </td>
                      <td>{content.posted ? '게시중' : '게시 안 함'}</td>
                      <td>
                        {content.periodStart || content.periodEnd
                          ? `${content.periodStart ? kstDateTime(content.periodStart) : '시작 제한 없음'} ~ ${content.periodEnd ? kstDateTime(content.periodEnd) : '종료 제한 없음'}`
                          : '제한 없음'}
                      </td>
                      <td>{content.sortSeq}</td>
                      <td>{content.updatedOn}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>등록된 콘텐츠가 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={(next) => `/mbr/contents?type=${type}${next > 1 ? `&page=${next}` : ''}`} />
          </>
        )}
      </section>
    </>
  );
}
