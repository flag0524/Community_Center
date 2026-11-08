// 회원 화면의 첨부 영역. 파일을 한 개씩 올리고 검사 상태를 보이며 검사를 통과한 파일만 내려받게 한다. 한도는 서버가 알려 준다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useId, useRef, useState, type ChangeEvent } from 'react';
import { ApiRequestError } from '../api/http';
import { deleteMyFile, myFileUrl, uploadMyFile, type MyFileList } from '../api/myFiles';
import { myFilesQuery } from '../api/queries';
import { errorMessage } from '../lib/errors';
import { FILE_STATUS_LABEL, fileSize } from '../lib/korean';
import { DeleteConfirm } from './DeleteConfirm';
import { FormMessage } from './FormMessage';

interface Problem {
  name: string;
  message: string;
}

// 올리기 전에 서버가 알려 준 한도로 먼저 걸러 큰 파일을 헛되이 보내지 않게 한다. 최종 판정은 서버가 한다.
function precheck(file: File, limits: MyFileList): string | null {
  const extension = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : '';
  if (!limits.allowedExtensions.includes(extension)) return `허용되지 않는 형식입니다. (${limits.allowedExtensions.join(', ')})`;
  if (file.size === 0) return '빈 파일은 올릴 수 없습니다.';
  if (file.size > limits.maxBytes) return `파일은 ${fileSize(limits.maxBytes)} 이하만 올릴 수 있습니다.`;
  return null;
}

const fieldMessages = (error: unknown) => (error instanceof ApiRequestError ? Object.values(error.body?.fields ?? {}).join(' ') : '');

export function MyFiles({ ownerPath, label, pollMs = 3000 }: { ownerPath: string; label: string; pollMs?: number }) {
  const queryClient = useQueryClient();
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const list = useQuery({ ...myFilesQuery(ownerPath), refetchInterval: (query) => (query.state.data?.items.some((item) => item.status === 'PENDING') ? pollMs : false) });
  const [problems, setProblems] = useState<Problem[]>([]);
  const [uploading, setUploading] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['my-files', ownerPath] });
  const remove = useMutation({
    mutationFn: (fileId: string) => deleteMyFile(fileId),
    onSuccess: () => {
      setRemoving(null);
      return refresh();
    },
  });

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (!list.data || files.length === 0) return;
    const failed: Problem[] = [];
    for (const file of files) {
      const reason = precheck(file, list.data);
      if (reason) {
        failed.push({ name: file.name, message: reason });
        continue;
      }
      setUploading(file.name);
      try {
        await uploadMyFile(ownerPath, file, crypto.randomUUID());
        await refresh();
      } catch (error) {
        failed.push({ name: file.name, message: fieldMessages(error) || errorMessage(error) });
      }
    }
    setUploading(null);
    setProblems(failed);
    if (input.current) input.current.value = '';
  };

  return (
    <section className="proto-files" aria-labelledby={`${inputId}-title`}>
      <h3 id={`${inputId}-title`}>{label}</h3>
      {list.isPending && <p role="status">불러오는 중입니다.</p>}
      {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
      {list.data && (
        <>
          {list.data.items.length > 0 ? (
            <ul aria-label={`${label} 목록`}>
              {list.data.items.map((file) => (
                <li key={file.fileId}>
                  <span>{file.status === 'SAFE' ? <a href={myFileUrl(file.fileId)} download>{file.fileName}</a> : file.fileName}</span>
                  <span>
                    {fileSize(file.sizeBytes)} · {FILE_STATUS_LABEL[file.status]}
                    {file.blockReason && ` · ${file.blockReason}`}
                  </span>
                  {list.data.canEdit && (
                    <button className="button secondary" type="button" aria-label={`제거 (${file.fileName})`} onClick={() => setRemoving(file.fileId)}>
                      제거
                    </button>
                  )}
                  {removing === file.fileId && (
                    <DeleteConfirm label={`파일 ${file.fileName}`} pending={remove.isPending} error={remove.isError ? errorMessage(remove.error) : ''} onDelete={() => remove.mutate(file.fileId)} onCancel={() => setRemoving(null)} />
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p>올린 파일이 없습니다.</p>
          )}
          {list.data.canEdit ? (
            <label className="field">
              파일 추가
              <input ref={input} id={inputId} type="file" multiple accept={list.data.allowedExtensions.map((extension) => `.${extension}`).join(',')} aria-describedby={`${inputId}-hint`} disabled={uploading !== null} onChange={(event) => void upload(event)} />
            </label>
          ) : (
            <p className="proto-hint">지금은 파일을 추가하거나 제거할 수 없습니다.</p>
          )}
          {list.data.canEdit && (
            <p className="proto-hint" id={`${inputId}-hint`}>
              {list.data.maxFiles}개까지, 한 개당 {fileSize(list.data.maxBytes)} 이하, {list.data.allowedExtensions.join(' · ')} 파일을 올릴 수 있습니다. 올리면 검사를 거친 뒤 내려받을 수 있습니다.
            </p>
          )}
          {uploading && <FormMessage text={`올리는 중입니다. ${uploading}`} />}
          {problems.length > 0 && (
            <div className="form-message is-error" role="alert">
              <ul>
                {problems.map((problem) => (
                  <li key={problem.name}>
                    {problem.name}: {problem.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}