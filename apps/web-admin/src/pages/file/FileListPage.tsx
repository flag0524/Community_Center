// 첨부파일 조회 화면. 소유 업무·검사 상태·파일명으로 좁혀 보고 파일 올리기는 소유 업무 화면에서 한다 (ADM-MBR-006)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { adminFileListQuery, type AdminFileParams } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { fileSize } from '../../lib/format';
import { FILE_OWNER, FILE_STATUS } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['ownerKind', 'status', 'q'] as const;

export function FileListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: AdminFileParams = {
    ownerKind: (params.get('ownerKind') as Schemas['FileOwnerKind'] | null) ?? undefined,
    status: (params.get('status') as Schemas['FileStatus'] | null) ?? undefined,
    q: params.get('q') ?? undefined,
    page,
  };
  const list = useQuery(adminFileListQuery(filters));
  const hrefFor = (next: number) => `/mbr/files${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>첨부파일</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>파일 목록</h2>
        </div>
        <p className="adm-notice">이 화면은 조회 전용입니다. 파일은 소유 업무 화면에서 올리고, 접근 권한이 있는 업무의 파일만 보입니다.</p>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="파일 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            void navigate(`/mbr/files${toQueryString(Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()])))}`);
          }}
        >
          <label>
            소유 업무
            <select name="ownerKind" defaultValue={filters.ownerKind ?? ''}>
              <option value="">전체</option>
              {Object.entries(FILE_OWNER).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            검사 상태
            <select name="status" defaultValue={filters.status ?? ''}>
              <option value="">전체</option>
              {Object.entries(FILE_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="wide">
            파일명
            <input name="q" defaultValue={filters.q} maxLength={100} />
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/mbr/files">
            조건 지우기
          </Link>
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="파일 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">파일명</th>
                    <th scope="col">소유 업무</th>
                    <th scope="col">크기</th>
                    <th scope="col">검사상태</th>
                    <th scope="col">등록일</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((file) => (
                    <tr key={file.fileId}>
                      <td>
                        <Link to={`/mbr/files/${file.fileId}`}>{file.fileName}</Link>
                      </td>
                      <td>
                        {FILE_OWNER[file.ownerKind]} · {file.ownerLabel}
                      </td>
                      <td>{fileSize(file.sizeBytes)}</td>
                      <td>{FILE_STATUS[file.status]}</td>
                      <td>{file.registeredOn}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 파일이 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}