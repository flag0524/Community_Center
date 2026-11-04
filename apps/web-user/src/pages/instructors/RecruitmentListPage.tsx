// 강사 모집공고 목록. 상태·공고명·모집기간·모집인원을 보이고 지원내역으로 이어 준다(FN-019)
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { recruitmentListQuery } from '../../api/queries';
import { Pager } from '../../components/Pager';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { formatDate, formatMonthDay } from '../../lib/format';
import { usePageTitle } from '../../lib/usePageTitle';
import { INSTRUCTOR_GROUP_TITLE, RECRUITMENT_STATUS_LABEL } from './labels';

const TITLE = '강사등록신청';

/** 2026.02.23–03.13 */
export const periodText = (start: string, end: string) => `${formatDate(start)}–${formatMonthDay(end)}`;

export function RecruitmentListPage() {
  usePageTitle(TITLE);
  const [searchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const query = useQuery(recruitmentListQuery(page));
  const group = NAV_GROUPS.find((item) => item.title === INSTRUCTOR_GROUP_TITLE)!;
  const data = query.data;

  return (
    <SubLayout group={group} title={TITLE} subtitle="" crumbs={[{ label: group.title }, { label: TITLE }]}>
      {!data ? (
        <QueryFallback query={query} what="모집공고" />
      ) : data.items.length === 0 ? (
        <div className="empty-state">
          <h3>등록된 모집공고가 없습니다.</h3>
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <table className="data-table" aria-label="강사 모집공고">
              <thead>
                <tr>
                  <th scope="col">상태</th>
                  <th scope="col">모집공고</th>
                  <th scope="col">모집기간</th>
                  <th scope="col">모집인원</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.recruitmentId}>
                    <td>{RECRUITMENT_STATUS_LABEL[item.status]}</td>
                    <td>
                      <Link to={`/instructors/recruit/${item.recruitmentId}`}>{item.title}</Link>
                    </td>
                    <td>{periodText(item.periodStart, item.periodEnd)}</td>
                    <td>{item.headcount ? `${item.headcount}명` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager
            page={data.page}
            totalPages={Math.ceil(data.total / data.size)}
            hrefFor={(next) => (next > 1 ? `/instructors/recruit?page=${next}` : '/instructors/recruit')}
          />
        </>
      )}
      <div className="proto-actions">
        <Link className="button" to="/me/instructor-applications">
          지원내역
        </Link>
      </div>
    </SubLayout>
  );
}