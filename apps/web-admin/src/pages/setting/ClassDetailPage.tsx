// 강좌분류 상세 화면. 이름·순서를 고치고 중지·재활성·삭제하며 변경 이력을 본다. 연결 강좌 수를 확인하지 못하면 중지·삭제를 막는다 (ADM-SYS-007 강좌분류)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { activateClass, deactivateClass, deleteClass, updateClass, type CourseClass } from '../../api/classes';
import { classHistoryQuery, classListQuery } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { Field, describe } from '../../components/Field';
import { TableWrap } from '../../components/ListParts';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { CLASS_ACTION } from '../../lib/labels';
import { allFieldMessages, isVersionConflict } from '../../lib/messages';

export function ClassDetailPage() {
  const { classId = '' } = useParams();
  const list = useQuery(classListQuery);
  if (list.isPending) return <p role="status">불러오는 중입니다.</p>;
  if (list.isError) return <p role="alert">{errorMessage(list.error)}</p>;
  const found = list.data.items.find((item) => item.classId === classId);
  if (!found) return <p role="alert">분류를 찾을 수 없습니다.</p>;
  return <ClassDetail key={found.classId} item={found} canEdit={list.data.canEdit} />;
}

function ClassDetail({ item, canEdit }: { item: CourseClass; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const history = useQuery(classHistoryQuery(item.classId));
  const [name, setName] = useState(item.name);
  const [sortSeq, setSortSeq] = useState(String(item.sortSeq));
  const [missing, setMissing] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['classes'] });
    setSaved(true);
  };
  const save = useMutation({ mutationFn: () => updateClass(item.classId, { name: name.trim(), sortSeq: Number(sortSeq) }, item.version), onSuccess: refresh });
  const deactivate = useMutation({ mutationFn: () => deactivateClass(item.classId, item.version), onSuccess: refresh });
  const activate = useMutation({ mutationFn: () => activateClass(item.classId, item.version), onSuccess: refresh });
  const remove = useMutation({
    mutationFn: () => deleteClass(item.classId, item.version),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['classes'] });
      void navigate('/sys/classes');
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!name.trim()) errors.name = '필수 항목입니다.';
    if (!/^[0-9]+$/.test(sortSeq)) errors.sortSeq = '0 이상의 정수를 입력해 주세요.';
    setMissing(errors);
    setSaved(false);
    if (Object.keys(errors).length === 0) save.mutate();
  };
  const server = fieldErrors(save.error);
  const err = (field: string) => missing[field] ?? server[field];
  const failure = [deactivate, activate, remove].find((mutation) => mutation.isError)?.error ?? (save.isError && Object.keys(server).length === 0 ? save.error : undefined);
  const blocked = item.courseCount === null ? '연결 강좌 수를 확인하지 못해 중지·삭제할 수 없습니다.' : item.courseCount > 0 ? `연결된 강좌가 ${item.courseCount}건 있어 중지·삭제할 수 없습니다.` : '';

  return (
    <>
      <div className="adm-page-heading">
        <h1>강좌분류 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>상태</dt>
        <dd>{item.active ? '사용' : '사용 안 함'}</dd>
        <dt>연결 강좌</dt>
        <dd>{item.courseCount == null ? '확인 실패' : `${item.courseCount}건`}</dd>
      </dl>
      <form className="adm-form" aria-label="분류" noValidate onSubmit={submit}>
        <fieldset disabled={!canEdit}>
          <div className="adm-form-grid">
            <Field id="class-name" label="분류명" required error={err('name')}>
              <input {...describe('class-name', err('name'))} value={name} onChange={(event) => { setName(event.target.value); setSaved(false); }} />
            </Field>
            <Field id="class-seq" label="순서" error={err('sortSeq')}>
              <input {...describe('class-seq', err('sortSeq'))} inputMode="numeric" value={sortSeq} onChange={(event) => { setSortSeq(event.target.value); setSaved(false); }} />
            </Field>
          </div>
        </fieldset>
        {saved && (
          <p className="adm-message" role="status">
            저장했습니다.
          </p>
        )}
        {failure !== undefined && (
          <p className="adm-message error" role="alert">
            {isVersionConflict(failure) ? '다른 곳에서 먼저 바뀌었습니다. 목록에서 다시 열어 주세요.' : allFieldMessages(failure) || errorMessage(failure)}
          </p>
        )}
        {blocked && item.active && <p className="adm-notice">{blocked}</p>}
        <div className="adm-actions">
          {canEdit && (
            <>
              <button className="adm-button" type="submit" disabled={save.isPending}>
                저장
              </button>
              {item.active ? (
                <ConfirmButton label="중지" confirmLabel="정말 중지" target={item.name} disabled={!item.canDeactivate || deactivate.isPending} onConfirm={() => deactivate.mutate()} />
              ) : (
                <button type="button" className="adm-button secondary" disabled={activate.isPending} onClick={() => activate.mutate()}>
                  재활성
                </button>
              )}
              <ConfirmButton label="삭제" confirmLabel="정말 삭제" target={item.name} disabled={!item.canDelete || remove.isPending} onConfirm={() => remove.mutate()} />
            </>
          )}
          <Link className="adm-button secondary" to="/sys/classes">
            목록
          </Link>
        </div>
      </form>

      <h2 className="adm-section">변경 이력</h2>
      {history.data && history.data.items.length > 0 ? (
        <TableWrap label="변경 이력">
          <table>
            <thead>
              <tr>
                <th scope="col">시각</th>
                <th scope="col">처리</th>
                <th scope="col">이전</th>
                <th scope="col">이후</th>
                <th scope="col">처리자</th>
              </tr>
            </thead>
            <tbody>
              {history.data.items.map((entry) => (
                <tr key={`${entry.at}-${entry.action}`}>
                  <td>{kstDateTime(entry.at)}</td>
                  <td>{CLASS_ACTION[entry.action]}</td>
                  <td>{entry.before ?? '-'}</td>
                  <td>{entry.after ?? '-'}</td>
                  <td>{entry.by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>{history.isPending ? '불러오는 중입니다.' : '변경 이력이 없습니다.'}</p>
      )}
    </>
  );
}