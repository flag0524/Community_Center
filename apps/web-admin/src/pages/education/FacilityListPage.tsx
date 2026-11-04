// 센터·강의실 화면. 센터 아래에 강의실을 묶어 트리로 보이고 사용 여부를 글자로 함께 알린다 (ADM-EDU-005)
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { facilityListQuery, type Facility } from '../../api/queries';
import { errorMessage } from '../../lib/errors';

const inUseLabel = (facility: Facility) => (facility.inUse ? '사용중' : '사용중지');

export function FacilityListPage() {
  const { data, isPending, isError, error } = useQuery(facilityListQuery);
  const centers = data?.items.filter((item) => item.kind === 'CENTER') ?? [];

  return (
    <>
      <div className="adm-page-heading">
        <h1>센터·강의실</h1>
      </div>
      <section className="adm-panel">
        <div className="adm-panel-head">
          <h2>센터·강의실 목록</h2>
          <Link className="adm-button" to="/edu/facilities/new">
            등록
          </Link>
        </div>
        {isPending && <p role="status">불러오는 중입니다.</p>}
        {isError && <p role="alert">{errorMessage(error)}</p>}
        {data && centers.length === 0 && <p>등록된 센터가 없습니다.</p>}
        {centers.length > 0 && (
          <ul className="adm-tree" aria-label="센터·강의실 트리">
            {centers.map((center) => (
              <li key={center.facilityId}>
                <FacilityLine facility={center} />
                <ul>
                  {data?.items
                    .filter((item) => item.parentId === center.facilityId)
                    .map((room) => (
                      <li key={room.facilityId}>
                        <FacilityLine facility={room} />
                      </li>
                    ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function FacilityLine({ facility }: { facility: Facility }) {
  return (
    <div className="adm-tree-line">
      <Link to={`/edu/facilities/${facility.facilityId}`}>{facility.name}</Link>
      <span className="adm-sub">
        {facility.kind === 'ROOM' && facility.floor ? `${facility.floor} · ` : ''}
        {inUseLabel(facility)} · 일정 {facility.scheduleCount}건
        {facility.isPublic ? '' : ' · 비공개'}
      </span>
    </div>
  );
}
