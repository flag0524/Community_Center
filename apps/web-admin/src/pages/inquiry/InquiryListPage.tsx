// 문의·답변 목록 화면. 답변을 기다리는 문의가 먼저 나오고 비공개 표시와 가려진 작성자를 보인다 (ADM-MBR-003)
import type { Schemas } from '@jori/api-client';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { adminInquiryCategoriesQuery, adminInquiryListQuery, type AdminInquiryParams } from '../../api/queries';
import { AdminPager, ResultCount, TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { INQUIRY_STATUS } from '../../lib/labels';
import { toQueryString } from '../../lib/queryString';

const PAGE_SIZE = 20;
const FILTERS = ['status', 'categoryId', 'q'] as const;

export function InquiryListPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const filters: AdminInquiryParams = {
    status: (params.get('status') as Schemas['InquiryStatus'] | null) ?? undefined,
    categoryId: params.get('categoryId') ?? undefined,
    q: params.get('q') ?? undefined,
    page,
  };
  const list = useQuery(adminInquiryListQuery(filters));
  const categories = useQuery(adminInquiryCategoriesQuery);

  const hrefFor = (next: number) =>
    `/mbr/inquiries${toQueryString({ ...Object.fromEntries(FILTERS.map((name) => [name, params.get(name)])), page: next > 1 ? next : undefined })}`;

  return (
    <>
      <div className="adm-page-heading">
        <h1>문의·답변</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>문의 목록</h2>
        </div>
        <form
          key={params.toString()}
          className="adm-toolbar"
          role="search"
          aria-label="문의 검색"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const next = Object.fromEntries(FILTERS.map((name) => [name, String(data.get(name) ?? '').trim()]));
            void navigate(`/mbr/inquiries${toQueryString(next)}`);
          }}
        >
          <label>
            답변 상태
            <select name="status" defaultValue={filters.status ?? ''}>
              <option value="">전체</option>
              {Object.entries(INQUIRY_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            분류
            <select name="categoryId" defaultValue={filters.categoryId ?? ''}>
              <option value="">전체 분류</option>
              {categories.data?.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="wide">
            검색어
            <input name="q" defaultValue={filters.q} placeholder="제목" maxLength={100} />
          </label>
          <button className="adm-button" type="submit">
            조회
          </button>
          <Link className="adm-button secondary" to="/mbr/inquiries">
            조건 지우기
          </Link>
        </form>
        {list.isPending && <p role="status">불러오는 중입니다.</p>}
        {list.isError && <p role="alert">{errorMessage(list.error)}</p>}
        {list.data && (
          <>
            <ResultCount total={list.data.total} />
            <TableWrap label="문의 목록">
              <table>
                <thead>
                  <tr>
                    <th scope="col">제목</th>
                    <th scope="col">분류</th>
                    <th scope="col">작성자</th>
                    <th scope="col">공개</th>
                    <th scope="col">답변상태</th>
                    <th scope="col">접수일</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((inquiry) => (
                    <tr key={inquiry.inquiryId}>
                      <td>
                        <Link to={`/mbr/inquiries/${inquiry.inquiryId}`}>{inquiry.title}</Link>
                      </td>
                      <td>{inquiry.categoryName}</td>
                      <td>{inquiry.authorName}</td>
                      <td>{inquiry.isPrivate ? '비공개' : '공개'}</td>
                      <td>{INQUIRY_STATUS[inquiry.status]}</td>
                      <td>{inquiry.receivedOn}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {list.data.items.length === 0 && <p>조건에 맞는 문의가 없습니다.</p>}
            <AdminPager page={page} total={list.data.total} size={PAGE_SIZE} hrefFor={hrefFor} />
          </>
        )}
      </section>
    </>
  );
}
