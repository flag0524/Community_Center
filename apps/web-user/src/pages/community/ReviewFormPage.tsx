// 수강후기 작성·수정. 후기를 쓸 수 있는 강좌(수강확정)만 고르게 하고, 없으면 양식을 보이지 않는다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { createReview, updateReview } from '../../api/community';
import { reviewQuery, reviewableCoursesQuery, type ReviewDetail } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { QueryFallback } from '../../components/QueryFallback';
import { TextField } from '../../components/TextField';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';
import { COMMUNITY_GROUP_TITLE } from '../board/boards';

const TITLE = '수강후기';

function ReviewForm({
  courses,
  initial,
  postId,
}: {
  courses: Array<{ courseId: string; name: string }>;
  initial?: ReviewDetail;
  postId?: string;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [courseId, setCourseId] = useState(initial?.courseId ?? courses[0]?.courseId ?? '');
  const [title, setTitle] = useState(initial?.title ?? '');
  const [body, setBody] = useState(initial?.body ?? '');
  const [errors, setErrors] = useState<{ title?: string; body?: string }>({});
  const idempotencyKey = useRef(crypto.randomUUID());
  const sending = useRef(false);

  const save = useMutation({
    mutationFn: () => {
      const payload = { courseId, title: title.trim(), body: body.trim() };
      return postId ? updateReview(postId, payload) : createReview(payload, idempotencyKey.current);
    },
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ['reviews'] });
      await queryClient.invalidateQueries({ queryKey: ['me'] });
      navigate(`/board/review/${saved.postId}`, { replace: true });
    },
    onSettled: () => {
      sending.current = false;
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const found = {
      title: title.trim() ? undefined : '제목을 입력해 주세요.',
      body: body.trim() ? undefined : '내용을 입력해 주세요.',
    };
    setErrors(found);
    if (found.title || found.body || sending.current) return;
    sending.current = true;
    save.mutate();
  }

  const server = fieldErrors(save.error);
  return (
    <form className="proto-form" aria-label="수강후기" noValidate onSubmit={submit}>
      <label className="field">
        수강 강좌
        <select value={courseId} disabled={Boolean(postId)} onChange={(event) => setCourseId(event.target.value)}>
          {(postId && initial ? [{ courseId: initial.courseId, name: initial.courseName }] : courses).map((item) => (
            <option key={item.courseId} value={item.courseId}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <TextField
        label="제목"
        name="title"
        type="text"
        maxLength={100}
        autoComplete="off"
        value={title}
        error={errors.title ?? server.title}
        onChange={(event) => setTitle(event.target.value)}
      />
      <label className="field">
        내용
        <textarea
          rows={7}
          maxLength={2000}
          value={body}
          aria-invalid={errors.body ? true : undefined}
          aria-describedby={errors.body ? 'review-body-error' : undefined}
          onChange={(event) => setBody(event.target.value)}
        />
      </label>
      {errors.body ?? server.body ? (
        <p className="field-error" id="review-body-error">
          {errors.body ?? server.body}
        </p>
      ) : null}
      <div className="proto-form-actions">
        <button className="button" type="submit" disabled={save.isPending}>
          {postId ? '수정' : '등록'}
        </button>
      </div>
      <FormMessage text={save.isError && Object.keys(server).length === 0 ? errorMessage(save.error) : ''} error />
    </form>
  );
}

export function ReviewFormPage({ mode }: { mode: 'create' | 'edit' }) {
  const { postId } = useParams();
  usePageTitle(`${TITLE} ${mode === 'edit' ? '수정' : '작성'}`);
  const courses = useQuery(reviewableCoursesQuery);
  const existing = useQuery({ ...reviewQuery(postId ?? ''), enabled: mode === 'edit' });
  const group = NAV_GROUPS.find((item) => item.title === COMMUNITY_GROUP_TITLE)!;

  let body;
  if (mode === 'edit') {
    body = existing.data ? (
      <ReviewForm courses={[]} initial={existing.data} postId={postId} />
    ) : (
      <QueryFallback query={existing} what="후기" />
    );
  } else if (!courses.data) {
    body = <QueryFallback query={courses} what="수강 강좌" />;
  } else if (courses.data.items.length === 0) {
    body = (
      <div className="empty-state" role="status">
        <h3>후기를 쓸 수 있는 수강확정 강좌가 없습니다.</h3>
      </div>
    );
  } else {
    body = <ReviewForm courses={courses.data.items} />;
  }

  return (
    <SubLayout
      group={group}
      title={TITLE}
      subtitle=""
      crumbs={[{ label: group.title }, { label: TITLE, to: '/board/review' }, { label: mode === 'edit' ? '후기 수정' : '후기 작성' }]}
    >
      {body}
    </SubLayout>
  );
}