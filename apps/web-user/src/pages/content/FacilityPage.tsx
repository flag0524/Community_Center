// 시설안내. 서버가 시설 테이블에서 내려준 센터와 강의실을 센터별 표(층·시설명)로 그린다
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { facilitiesQuery } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '시설안내';

export function FacilityPage() {
  usePageTitle(TITLE);
  const query = useQuery(facilitiesQuery);
  const group = NAV_GROUPS.find((item) => item.title === '센터소개')!;
  if (!query.data) return <QueryFallback query={query} what="시설 안내" />;

  const centers = query.data.items.filter((item) => item.kind === 'CENTER');
  return (
    <SubLayout group={group} title={TITLE} subtitle="센터와 강의실 안내입니다." crumbs={[{ label: group.title }, { label: TITLE }]}>
      {centers.length === 0 ? <p>등록된 시설이 없습니다.</p> : null}
      {centers.map((center) => {
        const rooms = query.data.items.filter((item) => item.parentId === center.facilityId);
        return (
          <section className="article-text" key={center.facilityId}>
            <h2 className="section-heading">{center.name}</h2>
            {center.address ? <p>{center.address}</p> : null}
            {rooms.length > 0 ? (
              <div className="table-wrap">
                <table aria-label={`${center.name} 표`}>
                  <thead>
                    <tr>
                      <th scope="col">층</th>
                      <th scope="col">시설</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rooms.map((room) => (
                      <tr key={room.facilityId}>
                        <td>{room.floor ?? '-'}</td>
                        <td>{room.name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
        );
      })}
      <p>
        <Link to="/center/contact">찾아오시는 길 →</Link>
      </p>
    </SubLayout>
  );
}
