// 위치 및 연락처. 센터 연락처 응답을 그대로 보이고 비어 있는 값은 확인 필요로 표시한다
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { contactQuery } from '../../api/queries';
import { ContentLink } from '../../components/ContentLink';
import { PhoneLink } from '../../components/PhoneLink';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '위치 및 연락처';
const UNKNOWN = '확인 필요';
// 기관이 지도 업체를 네이버로 정했다(2026-11-19, ADR-100). 지도 SDK의 키가 나오기 전에는 주소로 네이버 지도를 여는 링크만 둔다.
const NAVER_MAP_SEARCH = 'https://map.naver.com/p/search/';

export function ContactPage() {
  usePageTitle(TITLE);
  const query = useQuery(contactQuery);
  const contact = query.data;
  const group = NAV_GROUPS.find((item) => item.title === '센터소개')!;
  // 불러오는 동안 '확인 필요'가 먼저 보이지 않게 연락처가 올 때까지 기다린다.
  if (!contact) return <QueryFallback query={query} what="연락처" />;
  const address = [contact.postalCode ? `[${contact.postalCode}]` : null, contact.address].filter(Boolean).join(' ');
  const mapUrl = contact.address ? `${NAVER_MAP_SEARCH}${encodeURIComponent(contact.address)}` : null;

  return (
    <SubLayout
      group={group}
      title={TITLE}
      subtitle="조리읍 행정복지센터 3층 주민자치센터입니다."
      crumbs={[{ label: group.title }, { label: TITLE }]}
    >
      <dl className="details-grid">
        <div>
          <dt>주소</dt>
          <dd>{address || UNKNOWN}</dd>
        </div>
        <div>
          <dt>방문 위치</dt>
          <dd>{contact.floorInfo || UNKNOWN}</dd>
        </div>
        <div>
          <dt>수강 문의</dt>
          <dd>{contact.phone ? <PhoneLink number={contact.phone} /> : UNKNOWN}</dd>
        </div>
        <div>
          <dt>센터 대표</dt>
          <dd>{contact.adminOfficePhone ? <PhoneLink number={contact.adminOfficePhone} /> : UNKNOWN}</dd>
        </div>
        {contact.openHours ? (
          <div>
            <dt>운영 시간</dt>
            <dd>{contact.openHours}</dd>
          </div>
        ) : null}
        {contact.parking ? (
          <div>
            <dt>주차</dt>
            <dd>{contact.parking}</dd>
          </div>
        ) : null}
      </dl>
      <div className="button-row">
        {mapUrl ? (
          <ContentLink className="button" url={mapUrl}>
            네이버 지도에서 보기
          </ContentLink>
        ) : null}
        <Link className="button secondary" to="/center/facility">
          층별 시설 안내
        </Link>
      </div>
    </SubLayout>
  );
}