// 첨부파일 상세 화면. 검사 상태와 차단 사유, 내려받기 감사기록을 보이고 저장 위치는 보이지 않는다 (ADM-MBR-006)
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { adminFileQuery } from '../../api/queries';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { fileSize, kstDateTime } from '../../lib/format';
import { FILE_OWNER, FILE_PURPOSE, FILE_STATUS } from '../../lib/labels';

export function FileDetailPage() {
  const { fileId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(adminFileQuery(fileId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return (
    <>
      <div className="adm-page-heading">
        <h1>첨부파일 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>파일명</dt>
        <dd>{data.fileName}</dd>
        <dt>소유 업무</dt>
        <dd>
          {FILE_OWNER[data.ownerKind]} · {data.ownerLabel}
        </dd>
        <dt>용도</dt>
        <dd>{FILE_PURPOSE[data.purpose]}</dd>
        <dt>형식</dt>
        <dd>{data.mimeType}</dd>
        <dt>크기</dt>
        <dd>{fileSize(data.sizeBytes)}</dd>
        <dt>검사상태</dt>
        <dd>{FILE_STATUS[data.status]}</dd>
        <dt>등록일</dt>
        <dd>{data.registeredOn}</dd>
        <dt>해시 앞부분</dt>
        <dd>{data.hashPrefix}</dd>
      </dl>
      {data.blockReason && (
        <p className="adm-message error" role="alert">
          차단 사유 · {data.blockReason}
        </p>
      )}
      <h2 className="adm-section">내려받기 기록</h2>
      {data.downloads.length > 0 ? (
        <TableWrap label="내려받기 기록">
          <table>
            <thead>
              <tr>
                <th scope="col">시각</th>
                <th scope="col">내려받은 사람</th>
                <th scope="col">구분</th>
              </tr>
            </thead>
            <tbody>
              {data.downloads.map((entry) => (
                <tr key={`${entry.at}-${entry.by}`}>
                  <td>{kstDateTime(entry.at)}</td>
                  <td>{entry.by}</td>
                  <td>{entry.byAdmin ? '담당자' : '회원'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>내려받기 기록이 없습니다.</p>
      )}
      <div className="adm-actions">
        <Link className="adm-button secondary" to="/mbr/files">
          목록
        </Link>
      </div>
    </>
  );
}