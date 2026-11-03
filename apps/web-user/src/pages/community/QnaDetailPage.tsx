// 문의 상세. 본문과 센터 답변을 보이고 답변 전의 본인 문의만 수정, 본인 문의만 삭제한다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { deleteInquiry } from '../../api/community';
import { inquiryQuery } from '../../api/queries';
import { DeleteConfirm } from '../../components/DeleteConfirm';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { errorMessage } from '../../lib/errors';
import { formatDate } from '../../lib/format';
import { usePageTitle } from '../../lib/usePageTitle';
import { COMMUNITY_GROUP_TITLE, paragraphs } from '../board/boards';

const TITLE = '질문과 답변';

export function QnaDetailPage() {
  const { postId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery(inquiryQuery(postId));
  const post = query.data;
  usePageTitle(post?.title ?? TITLE);
  const [confirming, setConfirming] = useState(false);
  const group = NAV_GROUPS.find((item) => item.title === COMMUNITY_GROUP_TITLE)!;

  const remove = useMutation({
    mutationFn: () => deleteInquiry(postId),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: ['me', 'inquiry', postId] });
      await queryClient.invalidateQueries({ queryKey: ['me', 'inquiries'] });
      navigate('/board/qna', { replace: true });
    },
  });

  if (!post) return <QueryFallback query={query} what="문의" />;

  return (
    <SubLayout
      group={group}
      title={TITLE}
      subtitle=""
      crumbs={[{ label: group.title }, { label: TITLE, to: '/board/qna' }, { label: post.title }]}
    >
      <div className="article-head">
        <h2>{post.title}</h2>
        <p>
          {post.authorName} · {formatDate(post.publishedAt)}
          {post.isPrivate ? ' · 비공개' : ''}
        </p>
      </div>
      <div className="proto-article">
        {paragraphs(post.body).map((text) => (
          <p key={text}>{text}</p>
        ))}
      </div>
      {post.answer ? (
        <section className="proto-answer">
          <h3>센터 답변</h3>
          {paragraphs(post.answer.body).map((text) => (
            <p key={text}>{text}</p>
          ))}
        </section>
      ) : (
        <p className="proto-hint">아직 답변이 등록되지 않았습니다.</p>
      )}
      {confirming ? (
        <DeleteConfirm
          label="문의"
          pending={remove.isPending}
          error={remove.isError ? errorMessage(remove.error) : ''}
          onDelete={() => remove.mutate()}
          onCancel={() => setConfirming(false)}
        />
      ) : null}
      <div className="proto-actions">
        {post.canEdit ? (
          <Link className="button" to={`/board/qna/${post.postId}/edit`}>
            수정
          </Link>
        ) : null}
        {post.canDelete && !confirming ? (
          <button className="button secondary" type="button" onClick={() => setConfirming(true)}>
            삭제
          </button>
        ) : null}
        <Link className="button secondary" to="/board/qna">
          목록
        </Link>
      </div>
    </SubLayout>
  );
}