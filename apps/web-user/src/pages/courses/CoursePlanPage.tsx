// 강의계획서. 강좌 정보 아래에 등록된 계획 본문과 첨부 파일을 보여 주고 아직 없으면 추후 등록된다고 알린다
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { courseDetailQuery, coursePlanQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { instructorText } from '../../lib/course';
import { usePageTitle } from '../../lib/usePageTitle';

const formatSize = (bytes: number) => (bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`);

export function CoursePlanPage() {
  const { courseId = '' } = useParams();
  const courseQuery = useQuery(courseDetailQuery(courseId));
  const planQuery = useQuery(coursePlanQuery(courseId));
  usePageTitle('강의계획서');

  const course = courseQuery.data;
  const plan = planQuery.data;
  if (!course) return <QueryFallback query={courseQuery} what="강좌 정보" />;
  if (!plan) return <QueryFallback query={planQuery} what="강의계획서" />;

  const registered = Boolean(plan.planText || plan.planFile);
  return (
    <ServicePage
      title="강의계획서"
      crumbs={[
        { label: '강좌정보', to: '/courses' },
        { label: course.name, to: `/courses/${course.courseId}` },
        { label: '강의계획서' },
      ]}
    >
      <h2 className="section-heading">{course.name}</h2>
      <dl className="details-grid">
        <div>
          <dt>담당 강사</dt>
          <dd>{instructorText(course.instructorName)}</dd>
        </div>
        <div>
          <dt>정원</dt>
          <dd>{course.capacity}명</dd>
        </div>
      </dl>
      {registered ? (
        <section className="article-text">
          <h2 className="section-heading">강의계획</h2>
          {plan.planText ? <p className="plan-text">{plan.planText}</p> : null}
          {plan.planFile ? (
            <p>
              첨부{' '}
              <a href={`/api/v1/files/${plan.planFile.fileId}`} download>
                {plan.planFile.name} ({formatSize(plan.planFile.sizeBytes)})
              </a>
            </p>
          ) : null}
        </section>
      ) : (
        <div className="empty-state">
          <h3>등록된 강의계획서가 없습니다.</h3>
          <p>강의계획서는 추후 등록될 예정입니다.</p>
        </div>
      )}
      <div className="record-actions">
        <Link className="button secondary" to={`/courses/${course.courseId}`}>
          강좌 상세
        </Link>
      </div>
    </ServicePage>
  );
}
