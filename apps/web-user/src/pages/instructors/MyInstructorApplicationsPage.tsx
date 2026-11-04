// 강사신청내역. 지원 강좌·신청번호·처리상태를 보이고 서류 검토중·보완요청일 때만 지원서 수정을 보인다
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { instructorApplicationsQuery, sessionQuery } from '../../api/queries';
import { Pager } from '../../components/Pager';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';
import { APPLY_STATUS_LABEL } from './labels';

const TITLE = '강사신청내역';

export function MyInstructorApplicationsPage() {
  usePageTitle(TITLE);
  const [searchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const query = useQuery(instructorApplicationsQuery(page));
  const session = useQuery(sessionQuery);
  const data = query.data;
  if (!data) return <QueryFallback query={query} what="지원내역" />;

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: TITLE }]}>
      <div className="proto">
        {data.items.length === 0 ? (
          <div className="empty-state">
            <h3>지원내역이 없습니다.</h3>
          </div>
        ) : (
          data.items.map((item) => (
            <section key={item.applicationId}>
              <h2>{item.recruitmentTitle}</h2>
              <dl className="proto-info">
                <div>
                  <dt>지원 강좌</dt>
                  <dd>{item.desiredCourse}</dd>
                </div>
                <div>
                  <dt>신청번호</dt>
                  <dd>{item.applicationId}</dd>
                </div>
                <div>
                  <dt>지원자</dt>
                  <dd>{session.data?.member?.name ?? ''}</dd>
                </div>
                <div>
                  <dt>처리상태</dt>
                  <dd>
                    {/* dd에 다른 역할을 주면 목록 구조 규칙(axe definition-list)에 어긋나 안쪽 span에 둔다. */}
                    <span role="status">{APPLY_STATUS_LABEL[item.status]}</span>
                  </dd>
                </div>
              </dl>
              {item.canEdit ? (
                <div className="proto-actions">
                  <Link className="button" to={`/me/instructor-applications/${item.applicationId}/edit`}>
                    지원서 수정
                  </Link>
                </div>
              ) : null}
            </section>
          ))
        )}
        <Pager
          page={data.page}
          totalPages={Math.ceil(data.total / data.size)}
          hrefFor={(next) => (next > 1 ? `/me/instructor-applications?page=${next}` : '/me/instructor-applications')}
        />
        <div className="proto-actions">
          <Link className="button secondary" to="/instructors/recruit">
            모집공고
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}