// 결제 화면과 결제 결과 화면이 함께 쓰는 신청 정보 목록(강좌, 기간, 수강료, 신청번호 등)
import { Link } from 'react-router-dom';
import type { Application } from '../../api/queries';
import { formatFee, instructorText } from '../../lib/course';
import { formatDate } from '../../lib/format';
import { formatSchedule } from '../../lib/schedule';

export function ApplicationFacts({ application, applicantName }: { application: Application; applicantName?: string }) {
  const { course } = application;
  const schedule = formatSchedule(course.schedules);
  return (
    <dl className="proto-info">
      <div>
        <dt>강좌명</dt>
        <dd>
          <Link to={`/courses/${course.courseId}`}>{course.name}</Link>
        </dd>
      </div>
      <div>
        <dt>강사</dt>
        <dd>{instructorText(course.instructorName)}</dd>
      </div>
      <div>
        <dt>교육기간</dt>
        <dd>
          {formatDate(course.educationStart)} – {formatDate(course.educationEnd)}
        </dd>
      </div>
      <div>
        <dt>요일·시간</dt>
        <dd>{[schedule.days, schedule.times].filter(Boolean).join(' ')}</dd>
      </div>
      <div>
        <dt>수강료</dt>
        <dd>{formatFee(application.fee)}</dd>
      </div>
      <div>
        <dt>신청번호</dt>
        <dd>{application.applicationId}</dd>
      </div>
      {applicantName ? (
        <div>
          <dt>신청자</dt>
          <dd>{applicantName}</dd>
        </div>
      ) : null}
    </dl>
  );
}
