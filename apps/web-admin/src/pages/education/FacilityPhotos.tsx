// 시설·강의실 사진. 고른 사진을 올리기 전에 미리 보고, 올린 사진은 검사를 통과하면 보이며 대표를 정하고 제거한다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useId, useState, type ChangeEvent } from 'react';
import { deleteOwnerFile, downloadUrl, setMainPhoto, uploadOwnerFile } from '../../api/ownerFiles';
import { ownerFilesQuery } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { errorMessage } from '../../lib/errors';
import { fileSize } from '../../lib/format';
import { FILE_STATUS } from '../../lib/labels';
import { allFieldMessages } from '../../lib/messages';

const IMAGES = ['jpg', 'jpeg', 'png'];

interface Picked {
  key: string; // 올릴 때의 멱등키. 고를 때 정해 두어 다시 보내도 한 장만 저장된다
  file: File;
  url: string;
}
interface Problem {
  name: string;
  message: string;
}

const dataUrl = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });

const reason = (caught: unknown) => allFieldMessages(caught) || errorMessage(caught);

export function FacilityPhotos({ facilityId, name, pollMs = 3000 }: { facilityId: string; name: string; pollMs?: number }) {
  const ownerPath = `/facilities/${facilityId}`;
  const queryClient = useQueryClient();
  const id = useId();
  const list = useQuery({ ...ownerFilesQuery(ownerPath), refetchInterval: (query) => (query.state.data?.items.some((item) => item.status === 'PENDING') ? pollMs : false) });
  const [picked, setPicked] = useState<Picked[]>([]);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [uploading, setUploading] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['owner-files', ownerPath] });
  const remove = useMutation({ mutationFn: (fileId: string) => deleteOwnerFile(fileId), onSuccess: refresh });
  const main = useMutation({
    mutationFn: (fileId: string) => setMainPhoto(facilityId, fileId, crypto.randomUUID()),
    onSuccess: (result) => queryClient.setQueryData(ownerFilesQuery(ownerPath).queryKey, result),
  });

  const items = list.data?.items ?? [];
  const mainId = items.find((item) => item.status === 'SAFE')?.fileId; // 주민 화면이 먼저 보이는 사진
  const extensions = (list.data?.allowedExtensions ?? []).filter((extension) => IMAGES.includes(extension));
  const room = (list.data?.maxFiles ?? 0) - items.length - picked.length;

  const choose = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.target;
    const chosen = Array.from(input.files ?? []);
    input.value = '';
    if (!list.data) return;
    const accepted: File[] = [];
    const rejected: Problem[] = [];
    for (const file of chosen) {
      const extension = file.name.split('.').pop()!.toLowerCase();
      const message = !extensions.includes(extension)
        ? `이미지(${extensions.join(', ')})만 올릴 수 있습니다.`
        : file.size === 0
          ? '빈 파일은 올릴 수 없습니다.'
          : file.size > list.data.maxBytes
            ? `파일은 ${fileSize(list.data.maxBytes)} 이하만 올릴 수 있습니다.`
            : accepted.length >= room
              ? `사진은 ${list.data.maxFiles}장까지 올릴 수 있습니다.`
              : null;
      if (message) rejected.push({ name: file.name, message });
      else accepted.push(file);
    }
    setProblems(rejected);
    const next = await Promise.all(accepted.map(async (file) => ({ key: crypto.randomUUID(), file, url: await dataUrl(file) })));
    setPicked((current) => [...current, ...next]);
  };

  const upload = async () => {
    const failed: Problem[] = [];
    for (const item of picked) {
      setUploading(item.file.name);
      try {
        await uploadOwnerFile(ownerPath, item.file, item.key);
        await refresh();
      } catch (caught) {
        failed.push({ name: item.file.name, message: reason(caught) });
      }
      setPicked((current) => current.filter((other) => other.key !== item.key));
    }
    setUploading(null);
    setProblems(failed);
  };

  const failedAction = remove.error ?? main.error;

  return (
    <section className="adm-panel" aria-labelledby={`${id}-title`}>
      <div className="adm-panel-head">
        <h2 id={`${id}-title`}>시설 사진</h2>
      </div>
      {list.isPending && <p role="status">불러오는 중입니다.</p>}
      {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
      {list.data && (
        <>
          <p className="adm-field-hint" id={`${id}-hint`}>
            {list.data.maxFiles}장까지, 한 장당 {fileSize(list.data.maxBytes)} 이하의 jpg · png. 검사를 통과한 사진이 주민 시설안내에 보이고 대표 사진이 먼저 보입니다.
          </p>
          {items.length > 0 ? (
            <ul className="adm-photo-grid" aria-label="올린 사진">
              {items.map((file, index) => (
                <li key={file.fileId}>
                  <figure>
                    {file.status === 'SAFE' ? (
                      <img src={downloadUrl(file.fileId)} alt={`${name} 사진 ${index + 1}`} />
                    ) : (
                      <div className="adm-photo-wait">
                        {FILE_STATUS[file.status]}
                        {file.blockReason && ` · ${file.blockReason}`}
                      </div>
                    )}
                    <figcaption>
                      {file.fileName}
                      {file.fileId === mainId && <strong className="adm-photo-main">대표</strong>}
                    </figcaption>
                  </figure>
                  {list.data.canEdit && (
                    <div className="adm-photo-actions">
                      {file.status === 'SAFE' && file.fileId !== mainId && (
                        <button type="button" className="adm-button secondary" aria-label={`${file.fileName} 대표로 지정`} disabled={main.isPending} onClick={() => main.mutate(file.fileId)}>
                          대표로 지정
                        </button>
                      )}
                      <ConfirmButton label="제거" confirmLabel="정말 제거" target={file.fileName} disabled={remove.isPending} onConfirm={() => remove.mutate(file.fileId)} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p>올린 사진이 없습니다.</p>
          )}
          {failedAction && (
            <p className="adm-message error" role="alert">
              {reason(failedAction)}
            </p>
          )}
          {list.data.canEdit &&
            (items.length < list.data.maxFiles ? (
              <div className="adm-field full">
                <label htmlFor={id}>사진 선택</label>
                <div>
                  <input id={id} type="file" multiple accept={extensions.map((extension) => `.${extension}`).join(',')} aria-describedby={`${id}-hint`} disabled={uploading !== null} onChange={(event) => void choose(event)} />
                </div>
              </div>
            ) : (
              <p className="adm-notice">{list.data.maxFiles}장을 모두 올렸습니다. 바꾸려면 먼저 제거해 주세요.</p>
            ))}
          {picked.length > 0 && (
            <>
              <h3>올리기 전 미리보기</h3>
              <ul className="adm-photo-grid" aria-label="올리기 전 미리보기">
                {picked.map((item) => (
                  <li key={item.key}>
                    <figure>
                      <img src={item.url} alt={`고른 사진 ${item.file.name}`} />
                      <figcaption>
                        {item.file.name} · {fileSize(item.file.size)}
                      </figcaption>
                    </figure>
                  </li>
                ))}
              </ul>
              <div className="adm-actions">
                <button type="button" className="adm-button" disabled={uploading !== null} onClick={() => void upload()}>
                  {picked.length}장 올리기
                </button>
                <button type="button" className="adm-button secondary" disabled={uploading !== null} onClick={() => setPicked([])}>
                  선택 취소
                </button>
              </div>
            </>
          )}
          {uploading && (
            <p role="status" className="adm-state">
              올리는 중입니다. {uploading}
            </p>
          )}
          {problems.length > 0 && (
            <div className="adm-message error" role="alert">
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
