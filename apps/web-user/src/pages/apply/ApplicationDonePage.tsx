// 신청 접수 결과. 결제 대기, 무료·전액감면 등록, 대기신청을 서버가 판정한 표시 상태로 나누어 보여 준다
import { useQuery } from '@tanstack/react-query';
import { Link, Navigate, useParams } from 'react-router-dom';
import { applicationQuery, sessionQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { formatFee, instructorText } from '../../lib/course';
import { formatDate } from '../../lib/format';
import { formatSchedule } from '../../lib/schedule';
import { usePageTitle } from '../../lib/usePageTitle';

type Kind = 'due' | 'free' | 'wait';

const HEADINGS: Record<Kind, { title: string; heading: string }> = {
  due: { title: '수강신청 접수', heading: '수강신청이 접수되었습니다.' },
  free: { title: '무료·전액감면 등록', heading: '수강 등록이 완료되었습니다.' },
  wait: { title: '대기신청 접수', heading: '대기신청이 접수되었습니다.' },
};

export function ApplicationDonePage() {
  const { applicationId = '' } = useParams();
  const query = useQuery(applicationQuery(applicationId));
  const session = useQuery(sessionQuery);
  const application = query.data;
  const kind: Kind | null = !application
    ? null
    : application.displayState === 'WAITING'
      ? 'wait'
      : application.displayState === 'CONFIRMED_FREE'
        ? 'free'
        : application.displayState === 'PAYMENT_DUE'
          ? 'due'
          : null;
  usePageTitle(kind ? HEADINGS[kind].title : '수강신청 접수');

  if (!application) return <QueryFallback query={query} what="신청 정보" />;
  // 접수 직후 화면이 아닌 상태(만료·취소 등)는 신청 상세가 맡는다.
  if (!kind) return <Navigate to={`/me/applications/${application.applicationId}`} replace />;

  const { course } = application;
  const schedule = formatSchedule(course.schedules);
  const detail = `/me/applications/${application.applicationId}`;

  return (
    <ServicePage title={HEADINGS[kind].title} crumbs={[{ label: '회원서비스' }, { label: HEADINGS[kind].title }]}>
      <div className="proto">
        <div className="proto-result">
          <h2>{HEADINGS[kind].heading}</h2>
          {kind === 'due' ? <p>자리가 배정되었습니다. 결제기한 안에 수강료를 결제해 주세요.</p> : null}
          {kind === 'free' ? <p>납부금액은 0원이며 별도 결제가 필요하지 않습니다.</p> : null}
          {kind === 'wait' ? (
            <p>대기순번 {application.waitingRank}번 · 자리가 배정되면 결제하실 수 있습니다.</p>
          ) : null}
        </div>
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
          <div>
            <dt>신청자</dt>
            <dd>{session.data?.member?.name ?? ''}</dd>
          </div>
        </dl>
        {kind === 'free' ? <p className="proto-hint">감면 자격과 증빙 확인 절차는 운영 검토 후 확정합니다.</p> : null}
        {kind === 'wait' ? (
          <p className="proto-hint">
            취소·미결제 만료 시 다음 유효 대기자에게 자동 배정합니다. 새 유료 자리 배정 시 10분의 결제기한이 시작됩니다.
          </p>
        ) : null}
        <div className="proto-actions">
          {kind === 'due' && application.canPay ? (
            <Link className="button" to={`/payment/${application.applicationId}`}>
              결제하기
            </Link>
          ) : null}
          <Link className={kind === 'due' ? 'button secondary' : 'button'} to={detail}>
            신청 상세
          </Link>
          {kind === 'free' ? (
            <Link className="button secondary" to="/me/applications">
              신청내역
            </Link>
          ) : null}
          {kind === 'wait' ? (
            <Link className="button secondary" to="/courses">
              목록
            </Link>
          ) : null}
        </div>
      </div>
    </ServicePage>
  );
}
