// 소유 업무 화면의 첨부 영역. 파일을 한 개씩 올리고 검사 상태를 보이며 검사를 통과한 파일만 내려받게 한다. 한도는 서버가 알려 준다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useId, useRef, useState, type ChangeEvent } from 'react';
import { deleteOwnerFile, downloadUrl, uploadOwnerFile, type OwnerFileList } from '../api/ownerFiles';
import { ownerFilesQuery } from '../api/queries';
import { errorMessage } from '../lib/errors';
import { fileSize } from '../lib/format';
import { FILE_STATUS } from '../lib/labels';
import { allFieldMessages } from '../lib/messages';
import { ConfirmButton } from './ConfirmButton';
import { TableWrap } from './ListParts';

interface Problem {
  name: string;
  message: string;
}

// 올리기 전에 서버가 알려 준 한도로 먼저 걸러 큰 파일을 헛되이 보내지 않게 한다. 최종 판정은 서버가 한다.
function precheck(file: File, limits: OwnerFileList): string | null {
  const extension = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : '';
  if (!limits.allowedExtensions.includes(extension)) return `허용되지 않는 형식입니다. (${limits.allowedExtensions.join(', ')})`;
  if (file.size === 0) return '빈 파일은 올릴 수 없습니다.';
  if (file.size > limits.maxBytes) return `파일은 ${fileSize(limits.maxBytes)} 이하만 올릴 수 있습니다.`;
  return null;
}

export function OwnerFiles({ ownerPath, label, pollMs = 3000 }: { ownerPath: string; label: string; pollMs?: number }) {
  const queryClient = useQueryClient();
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const list = useQuery({ ...ownerFilesQuery(ownerPath), refetchInterval: (query) => (query.state.data?.items.some((item) => item.status === 'PENDING') ? pollMs : false) });
  const [problems, setProblems] = useState<Problem[]>([]);
  const [uploading, setUploading] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['owner-files', ownerPath] });
  const remove = useMutation({ mutationFn: (fileId: string) => deleteOwnerFile(fileId), onSuccess: refresh });

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
        await uploadOwnerFile(ownerPath, file, crypto.randomUUID());
        await refresh();
      } catch (error) {
        failed.push({ name: file.name, message: allFieldMessages(error) || errorMessage(error) });
      }
    }
    setUploading(null);
    setProblems(failed);
    if (input.current) input.current.value = '';
  };

  return (
    <section className="adm-panel" aria-labelledby={`${inputId}-title`}>
      <div className="adm-panel-head">
        <h2 id={`${inputId}-title`}>{label}</h2>
      </div>
      {list.isPending && <p role="status">불러오는 중입니다.</p>}
      {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
      {list.data && (
        <>
          {list.data.items.length > 0 ? (
            <TableWrap label={`${label} 목록`}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">파일명</th>
                    <th scope="col">크기</th>
                    <th scope="col">상태</th>
                    <th scope="col">관리</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((file) => (
                    <tr key={file.fileId}>
                      <td>{file.status === 'SAFE' ? <a href={downloadUrl(file.fileId)} download>{file.fileName}</a> : file.fileName}</td>
                      <td>{fileSize(file.sizeBytes)}</td>
                      <td>
                        {FILE_STATUS[file.status]}
                        {file.blockReason && ` · ${file.blockReason}`}
                      </td>
                      <td>{list.data.canEdit ? <ConfirmButton label="제거" confirmLabel="정말 제거" target={file.fileName} disabled={remove.isPending} onConfirm={() => remove.mutate(file.fileId)} /> : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          ) : (
            <p>올린 파일이 없습니다.</p>
          )}
          {remove.isError && (
            <p className="adm-message error" role="alert">
              {errorMessage(remove.error)}
            </p>
          )}
          {list.data.canEdit ? (
            <div className="adm-field full">
              <label htmlFor={inputId}>파일 추가</label>
              <div>
                <input ref={input} id={inputId} type="file" multiple accept={list.data.allowedExtensions.map((extension) => `.${extension}`).join(',')} aria-describedby={`${inputId}-hint`} disabled={uploading !== null} onChange={(event) => void upload(event)} />
                <p className="adm-field-hint" id={`${inputId}-hint`}>
                  {list.data.maxFiles}개까지, 한 개당 {fileSize(list.data.maxBytes)} 이하, {list.data.allowedExtensions.join(' · ')} 파일을 올릴 수 있습니다. 올리면 검사를 거친 뒤 내려받을 수 있습니다.
                </p>
              </div>
            </div>
          ) : (
            <p className="adm-notice">지금은 파일을 추가하거나 제거할 수 없습니다.</p>
          )}
          {uploading && (
            <p role="status" className="adm-state">
              올리는 중입니다. {uploading}
            </p>
          )}
          {problems.length > 0 && (
            <ul className="adm-message error" role="alert">
              {problems.map((problem) => (
                <li key={problem.name}>
                  {problem.name}: {problem.message}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}