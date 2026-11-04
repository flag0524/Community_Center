// 강사 모집공고 상세. 지원하기는 서버가 지원 가능이라고 한 공고에만 보인다
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { recruitmentQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { formatDate } from '../../lib/format';
import { usePageTitle } from '../../lib/usePageTitle';
import { INSTRUCTOR_GROUP_TITLE, RECRUITMENT_STATUS_LABEL } from './labels';
import { periodText } from './RecruitmentListPage';

const TITLE = '강사등록신청';

export function RecruitmentDetailPage() {
  const { recruitmentId = '' } = useParams();
  const query = useQuery(recruitmentQuery(recruitmentId));
  const post = query.data;
  usePageTitle(post?.title ?? TITLE);
  const group = NAV_GROUPS.find((item) => item.title === INSTRUCTOR_GROUP_TITLE)!;

  if (!post) return <QueryFallback query={query} what="모집공고" />;
  // 로그인한 회원이 이미 지원했으면 서버가 지원 가능을 끈다. 그 이유를 알려 준다.
  const alreadyApplied = post.status === 'OPEN' && !post.canApply;

  return (
    <SubLayout
      group={group}
      title={TITLE}
      subtitle=""
      crumbs={[{ label: group.title }, { label: TITLE, to: '/instructors/recruit' }, { label: post.title }]}
    >
      <div className="article-head">
        <h2>{post.title}</h2>
        <p>
          {formatDate(post.announcedOn)} 공고 · {RECRUITMENT_STATUS_LABEL[post.status]}
        </p>
      </div>
      <dl className="proto-info">
        <div>
          <dt>모집기간</dt>
          <dd>{periodText(post.periodStart, post.periodEnd)}</dd>
        </div>
        <div>
          <dt>모집인원</dt>
          <dd>{post.headcount ? `${post.headcount}명` : '-'}</dd>
        </div>
        <div>
          <dt>모집분야</dt>
          <dd>{post.field}</dd>
        </div>
      </dl>
      <section className="article-text">
        <h3>지원안내</h3>
        <p>{post.guide ?? '자격·제출서류·심사 세부사항은 공고 원본을 확인해야 합니다.'}</p>
      </section>
      {alreadyApplied ? <p className="proto-hint">이미 지원한 공고입니다.</p> : null}
      <div className="proto-actions">
        {post.canApply ? (
          <Link className="button" to={`/instructors/recruit/${post.recruitmentId}/apply`}>
            온라인 지원서 작성
          </Link>
        ) : null}
        {alreadyApplied ? (
          <Link className="button secondary" to="/me/instructor-applications">
            지원내역
          </Link>
        ) : null}
        <Link className="button secondary" to="/instructors/recruit">
          목록
        </Link>
      </div>
    </SubLayout>
  );
}