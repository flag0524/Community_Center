// 강좌분류 목록 화면. 분류를 순서대로 보이고 새 분류를 더하며 연결 강좌 수를 확인하지 못하면 0건이 아니라 확인 실패로 보인다 (ADM-SYS-007 강좌분류)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { createClass } from '../../api/classes';
import { classListQuery } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { TableWrap } from '../../components/ListParts';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

export function ClassListPage() {
  const queryClient = useQueryClient();
  const key = useIdempotencyKey();
  const list = useQuery(classListQuery);
  const [name, setName] = useState('');
  const [sortSeq, setSortSeq] = useState('0');
  const [missing, setMissing] = useState<Record<string, string>>({});
  const [added, setAdded] = useState(false);

  const mutation = useMutation({
    mutationFn: () => createClass({ name: name.trim(), sortSeq: Number(sortSeq) }, key.current()),
    onSuccess: () => {
      key.renew();
      void queryClient.invalidateQueries({ queryKey: ['classes'] });
      setName('');
      setAdded(true);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!name.trim()) errors.name = '필수 항목입니다.';
    if (!/^[0-9]+$/.test(sortSeq)) errors.sortSeq = '0 이상의 정수를 입력해 주세요.';
    setMissing(errors);
    setAdded(false);
    if (Object.keys(errors).length === 0) mutation.mutate();
  };
  const server = fieldErrors(mutation.error);
  const err = (field: string) => missing[field] ?? server[field];

  return (
    <>
      <div className="adm-page-heading">
        <h1>강좌분류</h1>
      </div>
      <p className="adm-notice">분류명은 공백과 대소문자를 정리해 비교하며, 삭제한 분류의 이름도 다시 쓸 수 없습니다. 연결된 강좌가 있는 분류는 중지하거나 삭제할 수 없습니다.</p>
      {list.data && list.data.uncategorizedCount != null && list.data.uncategorizedCount > 0 && (
        <p className="adm-notice">분류가 없는 강좌가 {list.data.uncategorizedCount}건 있습니다. 자동으로 옮기지 않으니 강좌 수정에서 직접 지정해 주세요.</p>
      )}
      {list.data?.canEdit && (
        <form className="adm-form" aria-label="분류 추가" noValidate onSubmit={submit}>
          <div className="adm-form-grid">
            <Field id="class-name" label="분류명" required error={err('name')}>
              <input {...describe('class-name', err('name'))} value={name} onChange={(event) => { setName(event.target.value); setAdded(false); }} />
            </Field>
            <Field id="class-seq" label="순서" error={err('sortSeq')}>
              <input {...describe('class-seq', err('sortSeq'))} inputMode="numeric" value={sortSeq} onChange={(event) => setSortSeq(event.target.value)} />
            </Field>
          </div>
          {added && (
            <p className="adm-message" role="status">
              추가했습니다.
            </p>
          )}
          {mutation.isError && Object.keys(server).length === 0 && (
            <p className="adm-message error" role="alert">
              {errorMessage(mutation.error)}
            </p>
          )}
          <div className="adm-actions">
            <button className="adm-button" type="submit" disabled={mutation.isPending}>
              추가
            </button>
          </div>
        </form>
      )}
      {list.isPending && <p role="status">불러오는 중입니다.</p>}
      {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
      {list.data && (
        <TableWrap label="분류 목록">
          <table>
            <thead>
              <tr>
                <th scope="col">순서</th>
                <th scope="col">분류명</th>
                <th scope="col">연결 강좌</th>
                <th scope="col">상태</th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((item) => (
                <tr key={item.classId}>
                  <td>{item.sortSeq}</td>
                  <td>
                    <Link to={`/sys/classes/${item.classId}`}>{item.name}</Link>
                  </td>
                  <td>{item.courseCount == null ? '확인 실패' : `${item.courseCount}건`}</td>
                  <td>{item.active ? '사용' : '사용 안 함'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </>
  );
}