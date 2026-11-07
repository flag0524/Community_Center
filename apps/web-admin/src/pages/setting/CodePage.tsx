// 공통 코드 화면. 그룹별로 표시명·순서·사용 여부만 고치고 코드값은 바꾸거나 지우지 않으며 저장이 거절되면 입력을 그대로 둔다 (ADM-SYS-007)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { updateCodes } from '../../api/codes';
import { codeGroupsQuery, codeListQuery, type CodeParams } from '../../api/queries';
import { TableWrap } from '../../components/ListParts';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { toQueryString } from '../../lib/queryString';
import type { Schemas } from '@jori/api-client';

interface RowValue {
  name: string;
  sortSeq: string;
  use: boolean;
}

export function CodePage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const groups = useQuery(codeGroupsQuery);
  const group = params.get('group') ?? groups.data?.items[0]?.id;
  const filters: CodeParams | null = group ? { group, q: params.get('q') ?? undefined, use: (params.get('use') as 'true' | 'false' | null) ?? undefined } : null;
  const list = useQuery({ ...codeListQuery(filters ?? { group: '' }), enabled: filters !== null });

  return (
    <>
      <div className="adm-page-heading">
        <h1>공통 코드</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>코드 목록</h2>
        </div>
        <p className="adm-notice">코드값과 그룹은 바꿀 수 없고 코드를 지우거나 새로 만들 수도 없습니다. 쓰지 않으려면 사용을 끕니다.</p>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="코드 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            void navigate(`/sys/codes${toQueryString({ group: String(data.get('group') ?? ''), q: String(data.get('q') ?? '').trim(), use: String(data.get('use') ?? '') })}`);
          }}
        >
          <label>
            코드 그룹
            <select name="group" defaultValue={group ?? ''}>
              {groups.data?.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="wide">
            검색어
            <input name="q" defaultValue={filters?.q} maxLength={100} placeholder="코드·표시명" />
          </label>
          <label>
            사용
            <select name="use" defaultValue={filters?.use ?? ''}>
              <option value="">전체</option>
              <option value="true">사용</option>
              <option value="false">사용 안 함</option>
            </select>
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/sys/codes">
            조건 지우기
          </Link>
        </form>
        {(groups.isPending || list.isPending) && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && filters && <CodeTable key={`${filters.group}|${filters.q ?? ''}|${filters.use ?? ''}`} list={list.data} />}
      </section>
    </>
  );
}

function CodeTable({ list }: { list: Schemas['CodeList'] }) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<Record<string, RowValue>>(() => Object.fromEntries(list.items.map((item) => [item.code, { name: item.name, sortSeq: String(item.sortSeq), use: item.use }])));
  const [missing, setMissing] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  const mutation = useMutation({
    mutationFn: () => updateCodes({ groupId: list.group.id, items: list.items.map((item) => ({ code: item.code, name: values[item.code]!.name.trim(), sortSeq: Number(values[item.code]!.sortSeq), use: values[item.code]!.use })) }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['codes'] });
      setSaved(true);
    },
  });

  const change = (code: string, patch: Partial<RowValue>) => {
    setSaved(false);
    setValues((current) => ({ ...current, [code]: { ...current[code]!, ...patch } }));
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    for (const item of list.items) {
      const value = values[item.code]!;
      if (!value.name.trim()) errors[`${item.code}.name`] = '표시명을 입력해 주세요.';
      if (!/^[0-9]+$/.test(value.sortSeq)) errors[`${item.code}.sortSeq`] = '0 이상의 정수를 입력해 주세요.';
    }
    setMissing(errors);
    setSaved(false);
    if (Object.keys(errors).length === 0) mutation.mutate();
  };
  const server = fieldErrors(mutation.error);
  const err = (name: string) => missing[name] ?? server[name];

  return (
    <form aria-label="코드 편집" noValidate onSubmit={submit}>
      <TableWrap label="코드 목록">
        <table>
          <thead>
            <tr>
              <th scope="col">코드</th>
              <th scope="col">표시명</th>
              <th scope="col">순서</th>
              <th scope="col">사용</th>
              <th scope="col">참조</th>
            </tr>
          </thead>
          <tbody>
            {list.items.map((item) => {
              const value = values[item.code]!;
              return (
                <tr key={item.code}>
                  <td>{item.code}</td>
                  <td>
                    <input aria-label={`${item.code} 표시명`} aria-invalid={err(`${item.code}.name`) ? true : undefined} value={value.name} maxLength={100} onChange={(event) => change(item.code, { name: event.target.value })} />
                    {err(`${item.code}.name`) && <p className="adm-field-error">{err(`${item.code}.name`)}</p>}
                  </td>
                  <td>
                    <input aria-label={`${item.code} 순서`} aria-invalid={err(`${item.code}.sortSeq`) ? true : undefined} inputMode="numeric" value={value.sortSeq} onChange={(event) => change(item.code, { sortSeq: event.target.value })} />
                    {err(`${item.code}.sortSeq`) && <p className="adm-field-error">{err(`${item.code}.sortSeq`)}</p>}
                  </td>
                  <td>
                    <input aria-label={`${item.code} 사용`} type="checkbox" checked={value.use} onChange={(event) => change(item.code, { use: event.target.checked })} />
                  </td>
                  <td>{item.refCount == null ? '확인 실패' : `${item.refCount.toLocaleString('ko-KR')}건`}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableWrap>
      {list.items.length === 0 && <p>조건에 맞는 코드가 없습니다.</p>}
      {saved && (
        <p className="adm-message" role="status">
          저장했습니다.
        </p>
      )}
      {mutation.isError && Object.keys(server).length === 0 && (
        <p className="adm-message error" role="alert">
          {errorMessage(mutation.error)}
        </p>
      )}
      {list.items.length > 0 && (
        <div className="adm-actions">
          <button className="adm-button" type="submit" disabled={mutation.isPending}>
            저장
          </button>
        </div>
      )}
    </form>
  );
}