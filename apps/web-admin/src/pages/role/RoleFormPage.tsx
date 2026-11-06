// 권한 배정 등록 화면. 내가 위임할 수 있는 역할만 고르고 역할·범위·유효기간을 한 행으로 정한다 (ADM-SYS-002P)
import type { Schemas } from '@jori/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createAssignment } from '../../api/roles';
import { assignmentOptionsQuery } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { ASSIGNMENT_SCOPE } from '../../lib/labels';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

export function RoleFormPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const options = useQuery(assignmentOptionsQuery);
  const [adminId, setAdminId] = useState('');
  const [roleId, setRoleId] = useState('');
  const [scope, setScope] = useState<Schemas['AssignmentScope'] | ''>('');
  const [dongId, setDongId] = useState('');
  const [validFrom, setValidFrom] = useState('');
  const [validTo, setValidTo] = useState('');
  const [missing, setMissing] = useState<Record<string, string>>({});

  const role = options.data?.roles.find((item) => item.id === roleId);
  const mutation = useMutation({
    mutationFn: () => createAssignment({ adminId, roleId, scope: scope as Schemas['AssignmentScope'], dongId: scope === 'DONG' ? dongId : null, validFrom, validTo: validTo || null }, key.current()),
    onSuccess: (result) => {
      key.renew();
      void queryClient.invalidateQueries({ queryKey: ['roles', 'list'] });
      void navigate(`/sys/roles/${result.assignmentId}`, { replace: true });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!adminId) errors.adminId = '필수 항목입니다.';
    if (!roleId) errors.roleId = '필수 항목입니다.';
    if (roleId && !scope) errors.scope = '범위를 선택해 주세요.';
    if (scope === 'DONG' && !dongId) errors.dongId = '동을 선택해 주세요.';
    if (!validFrom) errors.validFrom = '필수 항목입니다.';
    setMissing(errors);
    if (Object.keys(errors).length === 0) mutation.mutate();
  };
  const server = fieldErrors(mutation.error);
  const err = (name: string) => missing[name] ?? server[name];

  return (
    <>
      <div className="adm-page-heading">
        <h1>권한 배정 추가</h1>
      </div>
      <p className="adm-notice">배정은 고칠 수 없습니다. 바꾸려면 회수하고 새로 배정합니다. 내가 가진 권한·범위·기간 안에서만 줄 수 있고, 자기 자신에게는 줄 수 없습니다.</p>
      {options.isPending && <p role="status">불러오는 중입니다.</p>}
      {options.isError && <p role="alert">{errorMessage(options.error)}</p>}
      {options.data && (
        <form className="adm-form" aria-label="권한 배정" noValidate onSubmit={submit}>
          <div className="adm-form-grid">
            <Field id="role-admin" label="관리자" required error={err('adminId')}>
              <select {...describe('role-admin', err('adminId'))} value={adminId} onChange={(event) => setAdminId(event.target.value)}>
                <option value="">선택</option>
                {options.data.admins.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field id="role-role" label="역할" required error={err('roleId')} hint="내가 위임할 수 있는 역할만 보입니다.">
              <select
                {...describe('role-role', err('roleId'), '내가 위임할 수 있는 역할만 보입니다.')}
                value={roleId}
                onChange={(event) => {
                  const next = options.data.roles.find((item) => item.id === event.target.value);
                  setRoleId(event.target.value);
                  setScope(next?.scopes.length === 1 ? next.scopes[0]! : '');
                  setDongId('');
                }}
              >
                <option value="">선택</option>
                {options.data.roles.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </Field>
            {role && (
              <div className="adm-field full">
                <span>범위</span>
                <div>
                  {role.scopes.map((value) => (
                    <label key={value} className="adm-radio">
                      <input type="radio" name="scope" checked={scope === value} onChange={() => { setScope(value); setDongId(''); }} />
                      {ASSIGNMENT_SCOPE[value]}
                    </label>
                  ))}
                  {err('scope') && <p className="adm-field-error">{err('scope')}</p>}
                </div>
              </div>
            )}
            {scope === 'DONG' && (
              <Field id="role-dong" label="동" required error={err('dongId')}>
                <select {...describe('role-dong', err('dongId'))} value={dongId} onChange={(event) => setDongId(event.target.value)}>
                  <option value="">선택</option>
                  {options.data.dongs.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            <Field id="role-from" label="유효 시작일" required error={err('validFrom')}>
              <input {...describe('role-from', err('validFrom'))} type="date" value={validFrom} onChange={(event) => setValidFrom(event.target.value)} />
            </Field>
            <Field id="role-to" label="유효 종료일" error={err('validTo')} hint="비우면 기간 제한 없이 배정합니다.">
              <input {...describe('role-to', err('validTo'), '비우면 기간 제한 없이 배정합니다.')} type="date" value={validTo} onChange={(event) => setValidTo(event.target.value)} />
            </Field>
          </div>
          {role && (
            <>
              <h2 className="adm-section">이 역할이 주는 권한</h2>
              <ul className="adm-list">
                {role.authorities.map((authority) => (
                  <li key={authority}>{authority}</li>
                ))}
              </ul>
            </>
          )}
          {mutation.isError && Object.keys(server).length === 0 && (
            <p className="adm-message error" role="alert">
              {errorMessage(mutation.error)}
            </p>
          )}
          <div className="adm-actions">
            <button className="adm-button" type="submit" disabled={mutation.isPending}>
              배정
            </button>
            <Link className="adm-button secondary" to="/sys/roles">
              목록
            </Link>
          </div>
        </form>
      )}
    </>
  );
}