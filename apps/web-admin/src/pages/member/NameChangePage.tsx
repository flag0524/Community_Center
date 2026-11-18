// 이름 변경 검토 화면. 회원이 요청한 새 이름과 사유를 센터에서 확인한 증빙과 대조해 두 번 확인하고 승인·반려한다 (FN-031, ADR-090)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { decideNameChange } from '../../api/nameChanges';
import { nameChangeListQuery } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { NAME_CHANGE_STATE } from '../../lib/labels';
import { isStateConflict } from '../../lib/messages';

export function NameChangePage() {
  const [params] = useSearchParams();
  const decided = params.get('state') === 'DECIDED';
  const state = decided ? 'DECIDED' : 'PENDING';
  const list = useQuery(nameChangeListQuery(state));
  const queryClient = useQueryClient();
  const [note, setNote] = useState('');
  const mutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'approve' | 'reject' }) => decideNameChange(id, action, note),
    onSuccess: () => {
      setNote('');
      void queryClient.invalidateQueries({ queryKey: ['name-changes'] });
    },
    onError: (error) => {
      // 다른 담당자가 먼저 처리했다. 목록을 다시 읽는다.
      if (isStateConflict(error)) void queryClient.invalidateQueries({ queryKey: ['name-changes'] });
    },
  });

  return (
    <>
      <div className="adm-page-heading">
        <h1>이름 변경 검토</h1>
      </div>
      <p className="adm-notice">회원이 요청한 새 이름과 사유를 센터에서 확인한 증빙과 대조한 뒤 승인합니다. 승인하면 회원 이름이 바로 바뀝니다. 처리 메모는 회원에게도 보입니다.</p>
      <p>
        <Link className={decided ? 'adm-button secondary' : 'adm-button'} aria-current={decided ? undefined : 'page'} to="/mbr/name-changes">
          검토 중
        </Link>{' '}
        <Link className={decided ? 'adm-button' : 'adm-button secondary'} aria-current={decided ? 'page' : undefined} to="/mbr/name-changes?state=DECIDED">
          처리한 요청
        </Link>
      </p>
      {!decided && (
        <div className="adm-form">
          <label>
            처리 메모(선택)
            <input value={note} maxLength={300} onChange={(event) => setNote(event.target.value)} placeholder="승인·반려할 때 회원에게 남길 말" />
          </label>
        </div>
      )}
      {mutation.isError && (
        <p className="adm-message error" role="alert">
          {isStateConflict(mutation.error) ? '이미 다른 담당자가 처리했거나 정상 회원이 아니라 승인할 수 없습니다. 목록을 다시 확인해 주세요.' : errorMessage(mutation.error)}
        </p>
      )}
      {list.isPending && <p role="status">불러오는 중입니다.</p>}
      {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
      {list.data && (
        <>
          <TableWrap label="이름 변경 요청 목록">
            <table>
              <thead>
                <tr>
                  <th scope="col">요청일시</th>
                  <th scope="col">아이디</th>
                  <th scope="col">현재 이름</th>
                  <th scope="col">새 이름</th>
                  <th scope="col">사유</th>
                  <th scope="col">상태</th>
                  <th scope="col">{decided ? '처리' : '결정'}</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((item) => (
                  <tr key={item.requestId}>
                    <td>{kstDateTime(item.requestedAt)}</td>
                    <td>{item.loginId}</td>
                    <td>{item.currentNameMasked}</td>
                    <td>{item.requestedName}</td>
                    <td className="adm-pre">{item.reason}</td>
                    <td>{NAME_CHANGE_STATE[item.state]}</td>
                    <td>
                      {item.state === 'PENDING' ? (
                        <>
                          <ConfirmButton label="승인" confirmLabel="정말 승인" target={`${item.loginId} → ${item.requestedName}`} disabled={mutation.isPending} onConfirm={() => mutation.mutate({ id: item.requestId, action: 'approve' })} />
                          <ConfirmButton label="반려" confirmLabel="정말 반려" target={`${item.loginId} → ${item.requestedName}`} disabled={mutation.isPending} onConfirm={() => mutation.mutate({ id: item.requestId, action: 'reject' })} />
                        </>
                      ) : (
                        <>
                          {item.decidedBy ?? '-'} · {item.decidedAt ? kstDateTime(item.decidedAt) : '-'}
                          {item.decisionNote ? ` · ${item.decisionNote}` : ''}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          {list.data.items.length === 0 && <p>{decided ? '처리한 요청이 없습니다.' : '검토 중인 요청이 없습니다.'}</p>}
        </>
      )}
    </>
  );
}
