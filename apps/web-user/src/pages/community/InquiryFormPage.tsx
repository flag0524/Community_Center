// 문의 작성·수정. 분류는 서버가 준 목록에서 고르고 비공개가 기본이다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { createInquiry, updateInquiry } from '../../api/community';
import { inquiryCategoriesQuery, inquiryQuery, type InquiryDetail } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { QueryFallback } from '../../components/QueryFallback';
import { TextField } from '../../components/TextField';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';
import { COMMUNITY_GROUP_TITLE } from '../board/boards';

const TITLE = '질문과 답변';

function InquiryForm({
  categories,
  initial,
  postId,
}: {
  categories: Array<{ categoryId: string; name: string }>;
  initial?: InquiryDetail;
  postId?: string;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [categoryId, setCategoryId] = useState(initial?.categoryId ?? categories[0]?.categoryId ?? '');
  const [title, setTitle] = useState(initial?.title ?? '');
  const [body, setBody] = useState(initial?.body ?? '');
  const [isPrivate, setIsPrivate] = useState(initial?.isPrivate ?? true);
  const [errors, setErrors] = useState<{ title?: string; body?: string }>({});
  const idempotencyKey = useRef(crypto.randomUUID());
  const sending = useRef(false);

  const save = useMutation({
    mutationFn: () => {
      const payload = { categoryId, title: title.trim(), body: body.trim(), isPrivate };
      return postId ? updateInquiry(postId, payload) : createInquiry(payload, idempotencyKey.current);
    },
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ['me'] });
      navigate(`/board/qna/${saved.postId}`, { replace: true });
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
    <form className="proto-form" aria-label="문의" noValidate onSubmit={submit}>
      <label className="field">
        문의 분류
        <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
          {categories.map((item) => (
            <option key={item.categoryId} value={item.categoryId}>
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
        placeholder="제목을 입력해 주세요."
        value={title}
        error={errors.title ?? server.title}
        onChange={(event) => setTitle(event.target.value)}
      />
      <label className="field">
        내용
        <textarea
          rows={7}
          maxLength={2000}
          placeholder="문의 내용을 작성해 주세요."
          value={body}
          aria-invalid={errors.body ? true : undefined}
          aria-describedby={errors.body ? 'inquiry-body-error' : undefined}
          onChange={(event) => setBody(event.target.value)}
        />
      </label>
      {errors.body ?? server.body ? (
        <p className="field-error" id="inquiry-body-error">
          {errors.body ?? server.body}
        </p>
      ) : null}
      <label className="proto-check">
        <input type="checkbox" checked={isPrivate} onChange={(event) => setIsPrivate(event.target.checked)} /> 비공개 문의
      </label>
      <div className="proto-form-actions">
        <button className="button" type="submit" disabled={save.isPending}>
          {postId ? '수정' : '등록'}
        </button>
      </div>
      <FormMessage text={save.isError && Object.keys(server).length === 0 ? errorMessage(save.error) : ''} error />
    </form>
  );
}

export function InquiryFormPage({ mode }: { mode: 'create' | 'edit' }) {
  const { postId } = useParams();
  usePageTitle(`${TITLE} ${mode === 'edit' ? '수정' : '작성'}`);
  const categories = useQuery(inquiryCategoriesQuery);
  const existing = useQuery({ ...inquiryQuery(postId ?? ''), enabled: mode === 'edit' });
  const group = NAV_GROUPS.find((item) => item.title === COMMUNITY_GROUP_TITLE)!;

  return (
    <SubLayout
      group={group}
      title={TITLE}
      subtitle=""
      crumbs={[{ label: group.title }, { label: TITLE, to: '/board/qna' }, { label: mode === 'edit' ? '문의 수정' : '문의 작성' }]}
    >
      {!categories.data ? (
        <QueryFallback query={categories} what="문의 분류" />
      ) : mode === 'edit' && !existing.data ? (
        <QueryFallback query={existing} what="문의" />
      ) : (
        <InquiryForm categories={categories.data.items} initial={existing.data} postId={mode === 'edit' ? postId : undefined} />
      )}
    </SubLayout>
  );
}