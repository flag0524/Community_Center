// 질문과 답변 목록. 로그인한 회원에게 모든 문의의 분류·상태를 보이고 다른 회원의 비공개 문의는 서버가 가린 값 그대로 보인다
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { inquiryListQuery } from '../../api/queries';
import { Pager } from '../../components/Pager';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';
import { COMMUNITY_GROUP_TITLE } from '../board/boards';
import { INQUIRY_STATUS_LABEL } from './labels';

const TITLE = '질문과 답변';

export function QnaListPage() {
  usePageTitle(TITLE);
  const [searchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const query = useQuery(inquiryListQuery(page));
  const group = NAV_GROUPS.find((item) => item.title === COMMUNITY_GROUP_TITLE)!;
  const data = query.data;

  return (
    <SubLayout group={group} title={TITLE} subtitle="" crumbs={[{ label: group.title }, { label: TITLE }]}>
      <div className="proto-actions">
        <Link className="button" to="/board/qna/write">
          문의 작성
        </Link>
        <Link className="button secondary" to="/me/inquiries">
          내 문의
        </Link>
      </div>
      {!data ? (
        <QueryFallback query={query} what="문의 목록" />
      ) : data.items.length === 0 ? (
        <div className="empty-state">
          <h3>등록된 문의가 없습니다.</h3>
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <table className="data-table" aria-label="문의 목록">
              <thead>
                <tr>
                  <th scope="col">분류</th>
                  <th scope="col">제목</th>
                  <th scope="col">작성자</th>
                  <th scope="col">상태</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.postId}>
                    <td>{item.categoryName}</td>
                    <td>
                      {/* 가려진 제목은 열 수 없는 글이다. 서버가 가린 문구 그대로 링크 없이 보인다. */}
                      {item.isPrivate && !item.isMine ? item.title : <Link to={`/board/qna/${item.postId}`}>{item.title}</Link>}
                    </td>
                    <td>{item.authorName}</td>
                    <td>{INQUIRY_STATUS_LABEL[item.status]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager
            page={data.page}
            totalPages={Math.ceil(data.total / data.size)}
            hrefFor={(next) => (next > 1 ? `/board/qna?page=${next}` : '/board/qna')}
          />
        </>
      )}
    </SubLayout>
  );
}