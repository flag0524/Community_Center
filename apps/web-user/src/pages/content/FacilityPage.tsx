// 시설안내. 서버가 내려준 센터와 강의실을 센터별 표(층·시설명)로 그리고, 올린 사진이 있으면 센터 사진과 사진 열을 더한다
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { facilitiesQuery } from '../../api/queries';
import { PhotoButton, PhotoViewer, type PhotoSet } from '../../components/FacilityPhotos';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '시설안내';

export function FacilityPage() {
  usePageTitle(TITLE);
  const query = useQuery(facilitiesQuery);
  const [viewing, setViewing] = useState<PhotoSet | null>(null);
  const group = NAV_GROUPS.find((item) => item.title === '센터소개')!;
  if (!query.data) return <QueryFallback query={query} what="시설 안내" />;

  const centers = query.data.items.filter((item) => item.kind === 'CENTER');
  return (
    <SubLayout group={group} title={TITLE} subtitle="센터와 강의실 안내입니다." crumbs={[{ label: group.title }, { label: TITLE }]}>
      {centers.length === 0 ? <p>등록된 시설이 없습니다.</p> : null}
      {centers.map((center) => {
        const rooms = query.data.items.filter((item) => item.parentId === center.facilityId);
        // 강의실 사진이 하나도 없는 센터는 층·시설 표만 보인다
        const withPhotos = rooms.some((room) => room.photoUrls.length > 0);
        return (
          <section className="article-text" key={center.facilityId}>
            <h2 className="section-heading">{center.name}</h2>
            {center.address ? <p>{center.address}</p> : null}
            {center.photoUrls.length > 0 ? <PhotoButton name={center.name} urls={center.photoUrls} onOpen={setViewing} /> : null}
            {rooms.length > 0 ? (
              <div className="table-wrap">
                <table aria-label={`${center.name} 표`}>
                  <thead>
                    <tr>
                      <th scope="col">층</th>
                      <th scope="col">시설</th>
                      {withPhotos ? <th scope="col">사진</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {rooms.map((room) => (
                      <tr key={room.facilityId}>
                        <td>{room.floor ?? '-'}</td>
                        <td>{room.name}</td>
                        {withPhotos ? <td>{room.photoUrls.length > 0 ? <PhotoButton name={room.name} urls={room.photoUrls} onOpen={setViewing} /> : '사진 준비 중'}</td> : null}
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
      {viewing ? <PhotoViewer photos={viewing} onClose={() => setViewing(null)} /> : null}
    </SubLayout>
  );
}
