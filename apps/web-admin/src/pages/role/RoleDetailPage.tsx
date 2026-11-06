// 권한 배정 상세 화면. 역할·범위·유효기간과 주는 권한을 보이고 유효한 배정은 두 번 확인해 회수한다 (ADM-SYS-002P)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { revokeAssignment, type RoleAssignment } from '../../api/roles';
import { assignmentQuery } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { errorMessage } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { ASSIGNMENT_STATUS } from '../../lib/labels';
import { allFieldMessages, isVersionConflict } from '../../lib/messages';

export function RoleDetailPage() {
  const { assignmentId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(assignmentQuery(assignmentId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return <RoleDetail key={data.assignmentId} assignment={data} />;
}

function RoleDetail({ assignment }: { assignment: RoleAssignment }) {
  const queryClient = useQueryClient();
  const [done, setDone] = useState(false);
  const mutation = useMutation({
    mutationFn: () => revokeAssignment(assignment.assignmentId, assignment.version),
    onSuccess: (result) => {
      queryClient.setQueryData(assignmentQuery(result.assignmentId).queryKey, result);
      void queryClient.invalidateQueries({ queryKey: ['roles', 'list'] });
      setDone(true);
    },
  });

  return (
    <>
      <div className="adm-page-heading">
        <h1>권한 배정 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>관리자</dt>
        <dd>{assignment.adminName}</dd>
        <dt>역할</dt>
        <dd>{assignment.roleName}</dd>
        <dt>범위</dt>
        <dd>{assignment.scopeLabel}</dd>
        <dt>유효기간</dt>
        <dd>
          {assignment.validFrom} ~ {assignment.validTo ?? '제한 없음'}
        </dd>
        <dt>상태</dt>
        <dd>{ASSIGNMENT_STATUS[assignment.status]}</dd>
        <dt>부여</dt>
        <dd>
          {assignment.grantedBy} · {kstDateTime(assignment.grantedAt)}
        </dd>
      </dl>
      <h2 className="adm-section">이 역할이 주는 권한</h2>
      <ul className="adm-list">
        {assignment.authorities.map((authority) => (
          <li key={authority}>{authority}</li>
        ))}
      </ul>
      {done && (
        <p className="adm-message" role="status">
          회수했습니다. 이 배정의 권한은 더 이상 쓸 수 없습니다.
        </p>
      )}
      {mutation.isError && (
        <p className="adm-message error" role="alert">
          {isVersionConflict(mutation.error) ? '다른 곳에서 먼저 바뀌었습니다. 목록에서 다시 열어 주세요.' : allFieldMessages(mutation.error) || errorMessage(mutation.error)}
        </p>
      )}
      <div className="adm-actions">
        {assignment.canRevoke && <ConfirmButton label="회수" confirmLabel="정말 회수" target={`${assignment.adminName} ${assignment.roleName}`} disabled={mutation.isPending} onConfirm={() => mutation.mutate()} />}
        <Link className="adm-button secondary" to="/sys/roles">
          목록
        </Link>
      </div>
    </>
  );
}