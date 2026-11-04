// 강사 소개. 강의 분야와 담당 강좌를 보이고 경력·자격은 공식 자료가 있을 때만 보인다
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { instructorQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { toQueryString } from '../../lib/queryString';
import { usePageTitle } from '../../lib/usePageTitle';
import { INSTRUCTOR_GROUP_TITLE } from './labels';

const TITLE = '강사현황';

export function InstructorDetailPage() {
  const { instructorId = '' } = useParams();
  const query = useQuery(instructorQuery(instructorId));
  const instructor = query.data;
  usePageTitle(instructor?.name ?? TITLE);
  const group = NAV_GROUPS.find((item) => item.title === INSTRUCTOR_GROUP_TITLE)!;

  if (!instructor) return <QueryFallback query={query} what="강사 정보" />;

  return (
    <SubLayout
      group={group}
      title={TITLE}
      subtitle=""
      crumbs={[{ label: group.title }, { label: TITLE, to: '/instructors' }, { label: instructor.name }]}
    >
      <h2 className="section-heading">{instructor.name}</h2>
      <dl className="details-grid">
        <div>
          <dt>강의 분야</dt>
          <dd>{instructor.categoryName ?? '-'}</dd>
        </div>
        <div>
          <dt>담당 강좌</dt>
          <dd>{instructor.courseNames.join(', ')}</dd>
        </div>
      </dl>
      <section className="article-text">
        <h3>경력 및 자격</h3>
        {instructor.career ? (
          <p>{instructor.career}</p>
        ) : (
          <p className="muted">공식 시간표에는 경력·자격 정보가 수록되어 있지 않습니다.</p>
        )}
      </section>
      <div className="button-row">
        <Link className="button" to={`/courses${toQueryString({ q: instructor.name })}`}>
          담당 강좌 찾기
        </Link>
        <Link className="button secondary" to="/instructors">
          강사 목록
        </Link>
      </div>
    </SubLayout>
  );
}