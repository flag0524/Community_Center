// 수강후기 상세. 본인 후기만 수정·삭제할 수 있다(서버가 정한 가능 여부를 따른다)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { deleteReview } from '../../api/community';
import { reviewQuery } from '../../api/queries';
import { DeleteConfirm } from '../../components/DeleteConfirm';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { errorMessage } from '../../lib/errors';
import { formatDate } from '../../lib/format';
import { usePageTitle } from '../../lib/usePageTitle';
import { COMMUNITY_GROUP_TITLE, paragraphs } from '../board/boards';

const TITLE = '수강후기';

export function ReviewDetailPage() {
  const { postId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery(reviewQuery(postId));
  const post = query.data;
  usePageTitle(post?.title ?? TITLE);
  const [confirming, setConfirming] = useState(false);
  const group = NAV_GROUPS.find((item) => item.title === COMMUNITY_GROUP_TITLE)!;

  const remove = useMutation({
    mutationFn: () => deleteReview(postId),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: ['me', 'review', postId] });
      await queryClient.invalidateQueries({ queryKey: ['reviews'] });
      await queryClient.invalidateQueries({ queryKey: ['me', 'reviews'] });
      navigate('/board/review', { replace: true });
    },
  });

  if (!post) return <QueryFallback query={query} what="후기" />;

  return (
    <SubLayout
      group={group}
      title={TITLE}
      subtitle=""
      crumbs={[{ label: group.title }, { label: TITLE, to: '/board/review' }, { label: post.title }]}
    >
      <div className="article-head">
        <h2>{post.title}</h2>
        <p>
          {post.authorName} · {formatDate(post.publishedAt)}
        </p>
      </div>
      <p>수강 강좌 {post.courseName}</p>
      <div className="proto-article">
        {paragraphs(post.body).map((text) => (
          <p key={text}>{text}</p>
        ))}
      </div>
      {confirming ? (
        <DeleteConfirm
          label="후기"
          pending={remove.isPending}
          error={remove.isError ? errorMessage(remove.error) : ''}
          onDelete={() => remove.mutate()}
          onCancel={() => setConfirming(false)}
        />
      ) : null}
      <div className="proto-actions">
        {post.canEdit ? (
          <Link className="button" to={`/board/review/${post.postId}/edit`}>
            수정
          </Link>
        ) : null}
        {post.canDelete && !confirming ? (
          <button className="button secondary" type="button" onClick={() => setConfirming(true)}>
            삭제
          </button>
        ) : null}
        <Link className="button secondary" to="/board/review">
          목록
        </Link>
      </div>
    </SubLayout>
  );
}