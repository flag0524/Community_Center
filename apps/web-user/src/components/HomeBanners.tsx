// 홈의 배너. 서버가 게시 중인 것만 내려주며 이미지가 없으면 제목만 보인다
import type { HomeResponse } from '../api/queries';
import { ContentLink } from './ContentLink';

export function HomeBanners({ banners }: { banners: HomeResponse['banners'] }) {
  if (banners.length === 0) return null;
  return (
    <section className="home-banners wrap" aria-label="안내 배너">
      {banners.map((banner) => (
        <ContentLink key={banner.contentId} url={banner.linkUrl} className="home-banner">
          {banner.image ? <img src={banner.image.url} alt={banner.image.alt} loading="lazy" /> : null}
          <strong>{banner.title}</strong>
        </ContentLink>
      ))}
    </section>
  );
}