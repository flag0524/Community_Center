// 운영 설정 상세 화면. 기준값·설명·근거와 버전을 읽기만 한다 (ADM-SYS-004)
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { settingQuery } from '../../api/queries';
import { errorMessage } from '../../lib/errors';
import { OPER_RULE_STATUS } from '../../lib/labels';

export function SettingDetailPage() {
  const { settingId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(settingQuery(settingId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return (
    <>
      <div className="adm-page-heading">
        <h1>운영 기준 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>항목</dt>
        <dd>{data.name}</dd>
        <dt>현재 기준</dt>
        <dd>{data.value}</dd>
        <dt>상태</dt>
        <dd>{OPER_RULE_STATUS[data.status]}</dd>
        <dt>버전</dt>
        <dd>{data.version}</dd>
        <dt>수정일</dt>
        <dd>{data.updatedOn}</dd>
        <dt>설명·근거</dt>
        <dd className="adm-pre">{data.body}</dd>
      </dl>
      <div className="adm-actions">
        <Link className="adm-button secondary" to="/sys/settings">
          목록
        </Link>
      </div>
    </>
  );
}