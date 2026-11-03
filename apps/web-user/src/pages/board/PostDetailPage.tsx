// 게시물 상세. 공고의 핵심 항목, 본문, 이미지, 첨부파일을 그리고 다른 게시판의 번호는 찾을 수 없음으로 처리한다
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { postQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { formatDate } from '../../lib/format';
import { usePageTitle } from '../../lib/usePageTitle';
import { NotFound } from '../Placeholder';
import { BOARDS, COMMUNITY_GROUP_TITLE, fileUrl, paragraphs, type ReadBoardKey } from './boards';

export function PostDetailPage({ board }: { board: ReadBoardKey }) {
  const { postId = '' } = useParams();
  const query = useQuery(postQuery(postId));
  const post = query.data;
  usePageTitle(post?.title ?? BOARDS[board].title);
  const config = BOARDS[board];
  const group = NAV_GROUPS.find((item) => item.title === COMMUNITY_GROUP_TITLE)!;

  if (!post) return <QueryFallback query={query} what="게시물" />;
  // 다른 게시판의 번호를 이 주소로 열면 없는 것과 같게 처리한다.
  if (post.board !== board) return <NotFound />;

  return (
    <SubLayout
      group={group}
      title={config.title}
      subtitle=""
      crumbs={[{ label: group.title }, { label: config.title, to: config.path }, { label: post.title }]}
    >
      <h2>{post.title}</h2>
      <p className="record-meta">등록일 {formatDate(post.publishedAt)}</p>
      <div className="record-body">
        {post.facts.length > 0 ? (
          <dl className="details-grid">
            {post.facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.url ? <a href={fact.url}>{fact.value}</a> : fact.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {paragraphs(post.body).map((text) => (
          <p key={text}>{text}</p>
        ))}
      </div>
      {post.images.map((image) => (
        <img key={image.fileId} src={fileUrl(image.fileId)} alt={image.alt} />
      ))}
      {post.attachments.length > 0 ? (
        <div className="record-file">
          <strong>첨부파일</strong>
          <ul aria-label="첨부파일">
            {post.attachments.map((file) => (
              <li key={file.fileId}>
                <a href={fileUrl(file.fileId)} download>
                  {file.name}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="record-actions">
        <Link className="button secondary" to={config.path}>
          목록으로
        </Link>
      </div>
    </SubLayout>
  );
}