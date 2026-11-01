// 분야별 강좌 화면. 한 분야의 강좌를 쪽 나눔 없이 이름과 강사만 간단히 보여 준다
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { categoriesQuery, courseListQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { instructorText } from '../../lib/course';
import { usePageTitle } from '../../lib/usePageTitle';
import { NotFound } from '../Placeholder';

// 한 분야의 강좌를 한 번에 가져온다. 분야별 화면은 쪽을 나누지 않는다(시안).
const ALL_IN_CATEGORY = 50;

export function CategoryCoursesPage() {
  const { categoryId = '' } = useParams();
  const categories = useQuery(categoriesQuery);
  const list = useQuery(courseListQuery({ categoryId, size: ALL_IN_CATEGORY }));
  const category = categories.data?.items.find((item) => item.categoryId === categoryId);
  const title = category ? `${category.name} 강좌` : '분야별 강좌';
  usePageTitle(title);

  if (categories.isPending || list.isPending) return <QueryFallback query={categories.isPending ? categories : list} what="분야별 강좌" />;
  if (categories.isError || list.isError) return <QueryFallback query={categories.isError ? categories : list} what="분야별 강좌" />;
  if (!category) return <NotFound />;

  const cycle = list.data.criteria.cycle;
  return (
    <ServicePage title={title} crumbs={[{ label: '강좌정보', to: '/courses' }, { label: title }]}>
      <div className="result-line">
        <span>강좌 {list.data.total}개</span>
        {cycle ? <span>{cycle.name}</span> : null}
      </div>
      <div className="course-category-list">
        {list.data.items.map((course) => (
          <Link key={course.courseId} to={`/courses/${course.courseId}`}>
            <span>{course.name}</span>
            <small>{instructorText(course.instructorName)}</small>
          </Link>
        ))}
      </div>
      <div className="record-actions">
        <Link className="button secondary" to="/courses">
          전체 강좌
        </Link>
      </div>
    </ServicePage>
  );
}
