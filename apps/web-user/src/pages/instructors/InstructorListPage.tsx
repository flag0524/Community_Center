// 강사현황. 시간표에 수록된 승인·공개 강사를 강사명·강좌명으로 검색한다(FN-018)
import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { instructorListQuery } from '../../api/queries';
import { Pager } from '../../components/Pager';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { toQueryString } from '../../lib/queryString';
import { usePageTitle } from '../../lib/usePageTitle';
import { INSTRUCTOR_GROUP_TITLE } from './labels';

const TITLE = '강사현황';

export function InstructorListPage() {
  usePageTitle(TITLE);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const q = searchParams.get('q')?.trim() || undefined;
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const [text, setText] = useState(q ?? '');
  const query = useQuery(instructorListQuery({ q, page }));
  const group = NAV_GROUPS.find((item) => item.title === INSTRUCTOR_GROUP_TITLE)!;
  const data = query.data;

  function search(event: FormEvent) {
    event.preventDefault();
    navigate(`/instructors${toQueryString({ q: text.trim() || undefined })}`);
  }

  return (
    <SubLayout group={group} title={TITLE} subtitle="" crumbs={[{ label: group.title }, { label: TITLE }]}>
      <form className="toolbar" role="search" aria-label="강사·강좌 검색" onSubmit={search}>
        <label>
          강사·강좌 검색
          <input name="q" type="search" placeholder="강사명 또는 강좌명" value={text} onChange={(event) => setText(event.target.value)} />
        </label>
        <button className="button" type="submit">
          검색
        </button>
      </form>
      {!data ? (
        <QueryFallback query={query} what="강사 목록" />
      ) : data.items.length === 0 ? (
        <div className="empty-state">
          <h3>검색 결과가 없습니다.</h3>
        </div>
      ) : (
        <>
          <p className="muted">{q ? `검색된 강사 ${data.total}명` : `2026년 4분기 시간표에 수록된 강사 ${data.total}명`}</p>
          <div className="table-wrap">
            <table className="data-table" aria-label="강사 목록">
              <thead>
                <tr>
                  <th scope="col">강사명</th>
                  <th scope="col">분야</th>
                  <th scope="col">담당 강좌</th>
                  <th scope="col">소개</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.instructorId}>
                    <td>{item.name}</td>
                    <td>{item.categoryName ?? '-'}</td>
                    <td>{item.courseNames.join(', ')}</td>
                    <td>
                      {/* 이름이 보이는 글자를 낱말 단위로 포함해야 한다(WCAG 2.5.3). */}
                      <Link to={`/instructors/${item.instructorId}`} aria-label={`강사 소개 (${item.name})`}>
                        강사 소개
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager
            page={data.page}
            totalPages={Math.ceil(data.total / data.size)}
            hrefFor={(next) => `/instructors${toQueryString({ q, page: next > 1 ? next : undefined })}`}
          />
        </>
      )}
    </SubLayout>
  );
}