// 신청 취소 결과. 서버가 취소로 판정한 신청만 이 화면을 보이고 그 밖의 상태는 신청 상세로 보낸다
import { useQuery } from '@tanstack/react-query';
import { Link, Navigate, useParams } from 'react-router-dom';
import { applicationQuery, sessionQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';
import { ApplicationFacts } from '../payment/ApplicationFacts';

const TITLE = '신청 취소 결과';

export function ApplicationCancelledPage() {
  const { applicationId = '' } = useParams();
  const query = useQuery(applicationQuery(applicationId));
  const session = useQuery(sessionQuery);
  usePageTitle(TITLE);
  const application = query.data;

  if (!application) return <QueryFallback query={query} what="신청 정보" />;
  if (application.displayState !== 'CANCELLED') return <Navigate to={`/me/applications/${applicationId}`} replace />;

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: TITLE }]}>
      <div className="proto">
        <div className="proto-result">
          <h2>신청이 취소되었습니다.</h2>
          <p>{application.paymentStatus ? '신청이 취소되어 자리가 반환되었습니다.' : '미결제 신청이 취소되었습니다.'}</p>
        </div>
        <ApplicationFacts application={application} applicantName={session.data?.member?.name} />
        <div className="proto-actions">
          <Link className="button" to={`/apply/${application.course.courseId}`}>
            다시 신청하기
          </Link>
          <Link className="button secondary" to="/me/applications">
            신청내역
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}