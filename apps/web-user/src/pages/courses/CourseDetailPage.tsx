// 강좌 상세. 교육·접수 기간, 일정, 정원, 강사, 강의실과 접수 상태에 따른 수강신청 버튼을 보여 준다
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { courseDetailQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { categoryText, formatFee, instructorText, remainingSeatsText } from '../../lib/course';
import { formatDate } from '../../lib/format';
import { RECEPTION_LABEL } from '../../lib/reception';
import { formatSchedule } from '../../lib/schedule';
import { usePageTitle } from '../../lib/usePageTitle';

export function CourseDetailPage() {
  const { courseId = '' } = useParams();
  const query = useQuery(courseDetailQuery(courseId));
  const course = query.data;
  usePageTitle(course?.name ?? '강좌 상세');

  if (!course) return <QueryFallback query={query} what="강좌 정보" />;

  const schedule = formatSchedule(course.schedules);
  const seats = remainingSeatsText(course);
  const open = course.receptionState === 'OPEN';

  return (
    <ServicePage title={course.name} crumbs={[{ label: '강좌정보', to: '/courses' }, { label: course.name }]}>
      <div className="course-detail-layout">
        <div className="course-detail-content">
          <dl className="details-grid">
            <div>
              <dt>교육기간</dt>
              <dd>
                {formatDate(course.educationStart)} — {formatDate(course.educationEnd)}
              </dd>
            </div>
            <div>
              <dt>접수기간</dt>
              <dd>
                {formatDate(course.receptionStart)} — {formatDate(course.receptionEnd)}
              </dd>
            </div>
            <div>
              <dt>요일 · 시간</dt>
              <dd>{[schedule.days, schedule.times].filter(Boolean).join(' ')}</dd>
            </div>
            <div>
              <dt>정원</dt>
              <dd>{course.capacity}명</dd>
            </div>
            <div>
              <dt>담당 강사</dt>
              <dd>{instructorText(course.instructorName)}</dd>
            </div>
            <div>
              <dt>강의실</dt>
              <dd>{course.room ?? '미기재'}</dd>
            </div>
          </dl>
          <section className="article-text">
            <h2 className="section-heading">강의 안내</h2>
            {course.description ? <p>{course.description}</p> : null}
            <Link to={`/courses/${course.courseId}/plan`}>강의계획서 보기 →</Link>
          </section>
          <section className="article-text">
            <h2 className="section-heading">신청·결제 안내</h2>
            <p>유료 자리 배정 후 10분(600초) 안에 결제합니다.</p>
            <p>
              취소·미결제 만료 시 다음 유효 대기자에게 배정하며, 새로고침·재접속·결제수단 변경으로 기한이 늘어나지 않습니다.
            </p>
            <p>승인 결과 확인 중에는 재결제와 자리 반환을 보류합니다.</p>
          </section>
          <div className="button-row">
            <Link className="button secondary" to="/courses">
              강좌 목록
            </Link>
            <Link className="button secondary" to="/guide/refund">
              환불·휴강 안내
            </Link>
          </div>
        </div>
        <aside className="course-booking" aria-label="수강 정보">
          <p className="eyebrow">
            {[course.cycleName, categoryText(course.category)].filter(Boolean).join(' · ')}
          </p>
          <dl>
            <div>
              <dt>접수상태</dt>
              <dd>{RECEPTION_LABEL[course.receptionState]}</dd>
            </div>
            <div>
              <dt>정원</dt>
              <dd>
                {course.capacity}명{seats ? ` (${seats})` : ''}
              </dd>
            </div>
          </dl>
          <p>수강료</p>
          <div className="price">{formatFee(course.fee)}</div>
          {open ? (
            <Link className="button" to={`/apply/${course.courseId}`}>
              수강신청
            </Link>
          ) : (
            <button className="button secondary" type="button" disabled>
              {RECEPTION_LABEL[course.receptionState]}
            </button>
          )}
        </aside>
      </div>
    </ServicePage>
  );
}
