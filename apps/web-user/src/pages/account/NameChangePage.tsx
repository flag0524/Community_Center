// 이름 변경 요청. 새 이름·사유와 비밀번호를 보내고 센터가 증빙을 확인해 승인하면 이름이 바뀐다. 검토 중인 요청은 한 건뿐이다
import type { Schemas } from '@jori/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { requestNameChange } from '../../api/member';
import { nameChangesQuery, profileQuery } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { QueryFallback } from '../../components/QueryFallback';
import { TextField } from '../../components/TextField';
import { MyPageLayout } from '../../layout/SubLayout';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { formatDate } from '../../lib/format';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '이름 변경 요청';
const STATE: Record<Schemas['NameChangeState'], string> = { PENDING: '검토 중', APPROVED: '승인(이름이 바뀌었습니다)', REJECTED: '반려' };
const NAME_MAX = 50;
const REASON_MAX = 500;

function NameChangeForm({ currentName }: { currentName: string }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [reason, setReason] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ name?: string; reason?: string; password?: string }>({});
  const [sent, setSent] = useState(false);
  const key = useRef(crypto.randomUUID());

  const send = useMutation({
    mutationFn: () => requestNameChange({ newName: name.trim(), reason: reason.trim(), password }, key.current),
    onSuccess: async () => {
      key.current = crypto.randomUUID();
      setName('');
      setReason('');
      setPassword('');
      setSent(true);
      await queryClient.invalidateQueries({ queryKey: ['me'] });
    },
    onError: () => setPassword(''),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setSent(false);
    const found = {
      name: !name.trim() ? '바꾸려는 이름을 입력해 주세요.' : name.trim() === currentName ? '현재 이름과 같습니다.' : undefined,
      reason: reason.trim() ? undefined : '변경 사유를 입력해 주세요.',
      password: password ? undefined : '비밀번호를 입력해 주세요.',
    };
    setErrors(found);
    if (found.name || found.reason || found.password) return;
    send.mutate();
  }

  const server = fieldErrors(send.error);
  const message = send.isError && Object.keys(server).length === 0 ? errorMessage(send.error) : '';

  return (
    <form className="proto-form" aria-label="이름 변경 요청" noValidate onSubmit={submit}>
      <TextField label="바꾸려는 이름" name="newName" maxLength={NAME_MAX} autoComplete="off" value={name} error={errors.name ?? server.newName} onChange={(event) => setName(event.target.value)} />
      <label className="field">
        변경 사유
        <textarea name="reason" rows={3} maxLength={REASON_MAX} value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      {errors.reason && <p className="field-error">{errors.reason}</p>}
      <p className="proto-hint">신분증 등 증빙은 센터를 방문해 확인합니다. 증빙을 확인한 뒤 승인하면 이름이 바뀝니다.</p>
      <TextField
        label="비밀번호 확인"
        name="password"
        type="password"
        autoComplete="current-password"
        maxLength={64}
        value={password}
        error={errors.password ?? server.password}
        hint="본인 확인을 위해 현재 비밀번호를 다시 입력해 주세요."
        onChange={(event) => setPassword(event.target.value)}
      />
      <div className="proto-form-actions">
        <button className="button" type="submit" disabled={send.isPending}>
          요청
        </button>
      </div>
      <FormMessage text={sent ? '요청했습니다. 센터에서 확인한 뒤 알려 드립니다.' : message} error={!sent && send.isError} />
    </form>
  );
}

export function NameChangePage() {
  usePageTitle(TITLE);
  const profile = useQuery(profileQuery);
  const list = useQuery(nameChangesQuery);
  if (!profile.data) return <QueryFallback query={profile} what="회원정보" />;
  if (!list.data) return <QueryFallback query={list} what="이름 변경 요청" />;
  const pending = list.data.items.find((item) => item.state === 'PENDING');

  return (
    <MyPageLayout title={TITLE} crumbs={[{ label: '마이페이지' }, { label: '회원정보수정', to: '/me/profile' }, { label: TITLE }]}>
      <div className="proto">
        <dl className="proto-info">
          <div>
            <dt>현재 이름</dt>
            <dd>{profile.data.name}</dd>
          </div>
        </dl>
        {pending ? (
          <p className="proto-hint" role="status">
            {pending.requestedName}(으)로 바꾸는 요청을 센터에서 검토하고 있습니다. 처리가 끝나면 새 요청을 할 수 있습니다.
          </p>
        ) : (
          <NameChangeForm currentName={profile.data.name} />
        )}
        <h2>요청 내역</h2>
        {list.data.items.length === 0 ? (
          <p>요청한 내역이 없습니다.</p>
        ) : (
          <ul className="proto-list" aria-label="이름 변경 요청 내역">
            {list.data.items.map((item) => (
              <li key={item.requestId}>
                <strong>{item.requestedName}</strong> · {STATE[item.state]} · {formatDate(item.requestedAt)} 요청
                {item.decisionNote ? ` · 센터 안내: ${item.decisionNote}` : ''}
              </li>
            ))}
          </ul>
        )}
        <div className="proto-actions">
          <Link className="button secondary" to="/me/profile">
            회원정보수정
          </Link>
        </div>
      </div>
    </MyPageLayout>
  );
}
