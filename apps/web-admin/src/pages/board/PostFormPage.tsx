// 게시물 등록·수정 화면. 회원이 쓰는 게시판에는 새 글을 쓸 수 없고 회원이 쓴 글은 내용을 고칠 수 없다 (ADM-MBR-002P)
import type { Schemas } from '@jori/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { createPost, deletePost, updatePost, type AdminPost, type AdminPostWrite } from '../../api/boards';
import { adminPostQuery, boardListQuery, type BoardSettingList } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { Field, describe } from '../../components/Field';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { fromDateTimeInput, toDateTimeInput } from '../../lib/format';
import { isVersionConflict } from '../../lib/messages';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

interface Values {
  boardKey: string;
  title: string;
  content: string;
  pinned: boolean;
  periodStart: string;
  periodEnd: string;
}

const fromPost = (post: AdminPost): Values => ({
  boardKey: post.boardKey,
  title: post.title,
  content: post.content,
  pinned: post.pinned,
  periodStart: post.periodStart ? toDateTimeInput(post.periodStart) : '',
  periodEnd: post.periodEnd ? toDateTimeInput(post.periodEnd) : '',
});

export function PostFormPage({ mode }: { mode: 'create' | 'edit' }) {
  const { postId = '' } = useParams();
  const boards = useQuery(boardListQuery);
  const post = useQuery({ ...adminPostQuery(postId), enabled: mode === 'edit' });
  const failed = boards.isError ? boards.error : post.isError ? post.error : null;
  if (failed) return <p role="alert">{errorMessage(failed)}</p>;
  if (!boards.data || (mode === 'edit' && !post.data)) return <p role="status">불러오는 중입니다.</p>;
  return <PostForm key={post.data?.postId ?? 'new'} boards={boards.data} post={mode === 'edit' ? post.data : undefined} />;
}

function PostForm({ boards, post }: { boards: BoardSettingList; post?: AdminPost }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  // 새 글은 회원이 쓰지 않고 사용 중인 게시판에만 쓸 수 있다. 선택지에서 미리 거르고 서버가 다시 검사한다.
  const writable = boards.items.filter((board) => !board.memberWrite && board.inUse);
  const [values, setValues] = useState<Values>(post ? fromPost(post) : { boardKey: writable[0]?.boardKey ?? '', title: '', content: '', pinned: false, periodStart: '', periodEnd: '' });
  const [missing, setMissing] = useState<Partial<Record<keyof Values, string>>>({});
  const [saved, setSaved] = useState(false);
  const readOnly = post !== undefined && !post.canEditContent;

  const body = (): AdminPostWrite => ({
    boardKey: values.boardKey as Schemas['BoardKey'],
    title: values.title.trim(),
    content: values.content,
    pinned: values.pinned,
    periodStart: values.periodStart ? fromDateTimeInput(values.periodStart) : null,
    periodEnd: values.periodEnd ? fromDateTimeInput(values.periodEnd) : null,
  });

  const save = useMutation({
    mutationFn: () => (post ? updatePost(post.postId, body(), post.version) : createPost(body(), key.current())),
    onSuccess: (result) => {
      key.renew();
      queryClient.removeQueries({ queryKey: ['posts', 'list'] });
      // 게시판 목록(글 수)은 지우지 않고 다시 읽게만 한다. 지우면 화면이 불러오는 중으로 돌아가 저장 안내가 사라진다.
      void queryClient.invalidateQueries({ queryKey: ['boards', 'list'] });
      if (post) {
        queryClient.setQueryData(adminPostQuery(result.postId).queryKey, result);
        setSaved(true);
      } else void navigate(`/mbr/posts/${result.postId}`, { replace: true });
    },
  });
  const remove = useMutation({
    mutationFn: () => deletePost(post!.postId),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ['posts'] });
      // 게시판 목록(글 수)은 지우지 않고 다시 읽게만 한다. 지우면 화면이 불러오는 중으로 돌아가 저장 안내가 사라진다.
      void queryClient.invalidateQueries({ queryKey: ['boards', 'list'] });
      void navigate('/mbr/posts', { replace: true });
    },
  });

  const set = <K extends keyof Values>(name: K, value: Values[K]) => {
    setSaved(false);
    setValues((current) => ({ ...current, [name]: value }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Partial<Record<keyof Values, string>> = {};
    if (!values.boardKey) errors.boardKey = '필수 항목입니다.';
    if (!values.title.trim()) errors.title = '필수 항목입니다.';
    if (!values.content.trim()) errors.content = '필수 항목입니다.';
    setMissing(errors);
    if (Object.keys(errors).length === 0) save.mutate();
  };

  const server = fieldErrors(save.error);
  const err = (name: keyof Values) => missing[name] ?? server[name];
  const boardName = boards.items.find((board) => board.boardKey === values.boardKey)?.name ?? values.boardKey;

  return (
    <>
      <div className="adm-page-heading">
        <h1>{post ? '게시물 수정' : '게시물 등록'}</h1>
      </div>
      {readOnly && <p className="adm-notice">회원이 쓴 글은 관리자가 고칠 수 없습니다. 부적절한 글은 삭제할 수 있습니다.</p>}
      <form className="adm-form" aria-label="게시물" noValidate onSubmit={submit}>
        <fieldset disabled={readOnly}>
          <div className="adm-form-grid">
            <Field id="post-board" label="게시판" required error={err('boardKey')}>
              {post ? (
                <input {...describe('post-board')} value={boardName} readOnly />
              ) : (
                <select {...describe('post-board', err('boardKey'))} value={values.boardKey} onChange={(event) => set('boardKey', event.target.value)}>
                  <option value="">선택</option>
                  {writable.map((board) => (
                    <option key={board.boardKey} value={board.boardKey}>
                      {board.name}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field id="post-pinned" label="상단공지">
              <input {...describe('post-pinned')} type="checkbox" checked={values.pinned} onChange={(event) => set('pinned', event.target.checked)} />
            </Field>
            <Field id="post-title" label="제목" required error={err('title')} full>
              <input {...describe('post-title', err('title'))} value={values.title} maxLength={256} onChange={(event) => set('title', event.target.value)} />
            </Field>
            <Field id="post-content" label="본문" required error={err('content')} full hint="허용된 서식만 저장되고 나머지는 서버가 정리합니다.">
              <textarea {...describe('post-content', err('content'), '허용된 서식만 저장되고 나머지는 서버가 정리합니다.')} rows={10} maxLength={20000} value={values.content} onChange={(event) => set('content', event.target.value)} />
            </Field>
            <Field id="post-start" label="게시 시작" error={err('periodStart')} hint="비우면 바로 게시합니다.">
              <input {...describe('post-start', err('periodStart'), '비우면 바로 게시합니다.')} type="datetime-local" value={values.periodStart} onChange={(event) => set('periodStart', event.target.value)} />
            </Field>
            <Field id="post-end" label="게시 종료" error={err('periodEnd')} hint="비우면 계속 게시합니다.">
              <input {...describe('post-end', err('periodEnd'), '비우면 계속 게시합니다.')} type="datetime-local" value={values.periodEnd} onChange={(event) => set('periodEnd', event.target.value)} />
            </Field>
          </div>
        </fieldset>
        {saved && (
          <p className="adm-message" role="status">
            저장했습니다.
          </p>
        )}
        {save.isError && Object.keys(server).length === 0 && (
          <p className="adm-message error" role="alert">
            {isVersionConflict(save.error) ? '다른 곳에서 먼저 수정되었습니다. 목록에서 다시 열어 주세요.' : errorMessage(save.error)}
          </p>
        )}
        {remove.isError && (
          <p className="adm-message error" role="alert">
            {errorMessage(remove.error)}
          </p>
        )}
        <div className="adm-actions">
          {!readOnly && (
            <button className="adm-button" type="submit" disabled={save.isPending}>
              저장
            </button>
          )}
          {post && <ConfirmButton label="삭제" confirmLabel="정말 삭제" target={post.title} disabled={remove.isPending} onConfirm={() => remove.mutate()} />}
          <Link className="adm-button secondary" to="/mbr/posts">
            목록
          </Link>
        </div>
      </form>
    </>
  );
}
