// 홈 화면. 시안 index.html을 옮겼고 접수 상태·기간·소식·연락처는 API 응답을 그대로 그린다
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { homeQuery, type HomeResponse } from '../api/queries';
import { ArrowIcon, CardIcon, ListIcon, PinIcon, SearchIcon } from '../components/icons';
import { PhoneLink } from '../components/PhoneLink';
import { useContact } from '../layout/useContact';
import { formatDate, formatKoreanMonthDay, formatMonthDay, formatPeriod } from '../lib/format';
import { RECEPTION_LABEL, RECEPTION_SENTENCE } from '../lib/reception';
import { BUILDING_PHOTO, usePhoto } from '../lib/usePhoto';
import { usePageTitle } from '../lib/usePageTitle';

type Cycle = NonNullable<HomeResponse['cycle']>;

/** '조리읍 행정복지센터 3층'처럼 마지막 공백에서 줄을 나눈다. 공백이 없으면 그대로 둔다. */
function splitLastWord(text: string): [string, string | null] {
  const index = text.lastIndexOf(' ');
  return index < 0 ? [text, null] : [text.slice(0, index), text.slice(index + 1)];
}

function Hero() {
  const photo = usePhoto(BUILDING_PHOTO);
  return (
    <section className="hero">
      {photo === 'ok' ? <img src={BUILDING_PHOTO} alt="조리읍 행정복지센터 청사" /> : null}
      <div className="hero-copy">
        <div className="eyebrow">주민과 함께하는 배움의 공간</div>
        <h1>
          <span className="standard-only">
            함께 배우고,
            <br />
            함께 자라는 조리읍.
          </span>
          <span className="easy-only">무엇을 도와드릴까요?</span>
        </h1>
        <p>
          <span className="standard-only">일상에 새로운 즐거움을 더하는 조리읍주민자치센터</span>
          <span className="easy-only">원하시는 일을 선택해 주세요.</span>
        </p>
        <Link className="button" to="/courses">
          강좌 둘러보기　→
        </Link>
      </div>
      <a className="scroll-hint" href="#services">
        아래로 내려보기　↓
      </a>
      {photo === 'ok' ? <div className="photo-credit">조리읍 행정복지센터 · 파주시 제공(2022.10.05)</div> : null}
    </section>
  );
}

function EasyStart() {
  const contact = useContact();
  const photo = usePhoto(BUILDING_PHOTO);
  const actions = [
    { to: '/courses', icon: <SearchIcon />, title: '강좌 찾아보기', text: '분야와 시간으로 수업을 찾아보세요.' },
    { to: '/guide/apply', icon: <CardIcon />, title: '신청 방법 알아보기', text: '처음 신청하실 때 순서대로 알려드려요.' },
    { to: '/me/applications', icon: <ListIcon />, title: '내가 신청한 강좌 확인', text: '로그인 후 신청·결제 내역을 확인해요.' },
    { to: '/center/contact', icon: <PinIcon />, title: '센터 찾아오는 길', text: '주소와 위치를 확인하세요.' },
  ];
  return (
    <section className="easy-only easy-start wrap" aria-label="주요 서비스">
      <div className="easy-actions">
        {actions.map((action) => (
          <Link key={action.to} to={action.to}>
            {action.icon}
            <div>
              <strong>{action.title}</strong>
              <small>{action.text}</small>
            </div>
            <span className="go" aria-hidden="true">
              →
            </span>
          </Link>
        ))}
      </div>
      <div className="easy-place">
        {photo === 'ok' ? (
          <figure>
            <img src={BUILDING_PHOTO} alt="조리읍 행정복지센터 건물" />
            <figcaption>조리읍주민자치센터 · {contact?.floorInfo ?? '위치 확인 필요'}</figcaption>
          </figure>
        ) : null}
        <p className="phone-label">궁금한 점은 전화로 물어보세요.</p>
        {contact?.phone ? (
          <a className="phone" href={`tel:${contact.phone}`}>
            {contact.phone}
          </a>
        ) : (
          <span className="phone">전화번호 확인 필요</span>
        )}
      </div>
    </section>
  );
}

function EasyNotice({ cycle, firstNoticeId }: { cycle: Cycle; firstNoticeId: string | undefined }) {
  return (
    <section className="easy-only easy-home-notice">
      <div className="wrap">
        <div>
          <h2>{cycle.name} 교육프로그램</h2>
          <p>
            {RECEPTION_SENTENCE[cycle.receptionState]} 교육기간은 {formatKoreanMonthDay(cycle.educationStart)} ~{' '}
            {formatKoreanMonthDay(cycle.educationEnd)}입니다.
          </p>
        </div>
        <Link className="button secondary" to={firstNoticeId ? `/board/notice/${firstNoticeId}` : '/board/notice'}>
          모집 안내 읽기
        </Link>
      </div>
    </section>
  );
}

function Intro() {
  const items = [
    { to: '/courses', icon: <SearchIcon />, title: '강좌 찾기', lines: ['분야와 시간에 맞는', '강좌를 살펴보세요.'] },
    { to: '/me/applications', icon: <ListIcon />, title: '내 수강신청', lines: ['신청한 강좌와', '결제내역을 확인하세요.'] },
    { to: '/guide/apply', icon: <CardIcon />, title: '수강·결제 안내', lines: ['처음 신청하실 때', '필요한 안내입니다.'] },
    { to: '/center/contact', icon: <PinIcon />, title: '위치·연락처', lines: ['센터 위치와', '문의 전화를 확인하세요.'] },
  ];
  return (
    <section id="services" className="home-intro wrap">
      <div className="intro-heading">
        <h2>
          이웃과 함께하는 <span className="blue">배움,</span>
          <br />
          조리읍에서 시작하세요.
        </h2>
        <div className="intro-note">
          <strong>조리읍주민자치센터는</strong>
          <p>
            취미와 교양, 건강한 일상까지
            <br />
            주민의 배움을 함께하는 공간입니다.
          </p>
        </div>
      </div>
      <div className="service-strip">
        {items.map((item) => (
          <Link key={item.to} to={item.to}>
            <span className="icon-disc">{item.icon}</span>
            <div>
              <h3>{item.title}</h3>
              <p>
                {item.lines[0]}
                <br />
                {item.lines[1]}
              </p>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

function News({ home }: { home: HomeResponse }) {
  const contact = useContact();
  const [floorHead, floorTail] = splitLastWord(contact?.floorInfo ?? '');
  return (
    <section className="home-news wrap">
      <div>
        <div className="news-heading">
          <h2>센터 소식</h2>
          <Link className="news-tab current" to="/board/notice">
            공지사항
          </Link>
          <Link className="news-tab" to="/board/news">
            기관소식
          </Link>
          <Link className="news-tab" to="/board/resources">
            자료실
          </Link>
          <Link className="plus" to="/board/notice" aria-label="공지사항 더보기">
            +
          </Link>
        </div>
        {home.notices.map((notice) => (
          <Link key={notice.postId} className="notice-link" to={`/board/notice/${notice.postId}`}>
            <span>공지</span>
            <strong>{notice.title}</strong>
            <time dateTime={notice.publishedAt}>{formatDate(notice.publishedAt)}</time>
          </Link>
        ))}
      </div>
      <div>
        {home.cycle ? (
          <div className="program-banner">
            <div className="eyebrow">{home.cycle.name}</div>
            <h2>교육프로그램 안내</h2>
            <small>교육기간</small>
            <div className="period">
              {formatMonthDay(home.cycle.educationStart)} — {formatMonthDay(home.cycle.educationEnd)}
            </div>
            <p>{RECEPTION_LABEL[home.cycle.receptionState]} · 강좌별 상세 일정 확인</p>
            <Link to="/courses">
              전체 강좌 보기 <ArrowIcon />
            </Link>
          </div>
        ) : null}
        <div className="contact-strip">
          <div>
            수강·센터 이용 문의
            <strong>
              <PhoneLink number={contact?.phone} />
            </strong>
          </div>
          <p>
            {floorHead}
            {floorTail ? (
              <>
                <br />
                {floorTail}
              </>
            ) : null}
          </p>
        </div>
      </div>
    </section>
  );
}

function CourseGuide({ home }: { home: HomeResponse }) {
  return (
    <section className="home-courses wrap" aria-labelledby="course-guide-title">
      <div className="heading-line">
        <div>
          {home.cycle ? <div className="eyebrow">{home.cycle.name} 교육프로그램</div> : null}
          <h2 id="course-guide-title">
            강좌 <span className="blue">안내</span>
          </h2>
          <p>관심 있는 분야의 강좌와 일정을 살펴보세요.</p>
        </div>
        <Link to="/courses">전체 강좌 보기　+</Link>
      </div>
      <div className="category-grid" aria-label="분야별 강좌안내">
        {home.categories.map((item) => (
          <Link
            key={item.category.categoryId}
            className="category-item"
            to={`/courses/field/${item.category.categoryId}`}
          >
            <div className="category-title">
              <h3>{item.category.name}</h3>
              <span className="status">{RECEPTION_LABEL[item.receptionState]}</span>
            </div>
            <dl className="category-dates">
              <div>
                <dt>접수</dt>
                <dd>
                  {item.receptionStart && item.receptionEnd
                    ? formatPeriod(item.receptionStart, item.receptionEnd)
                    : '일정 확인 필요'}
                </dd>
              </div>
              <div>
                <dt>교육</dt>
                <dd>
                  {item.educationStart && item.educationEnd
                    ? formatPeriod(item.educationStart, item.educationEnd)
                    : '일정 확인 필요'}
                </dd>
              </div>
            </dl>
            <div className="category-courses">
              <p>{item.courseNames.join(' · ')}</p>
              <span aria-hidden="true">→</span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

function Gallery() {
  const contact = useContact();
  const photo = usePhoto(BUILDING_PHOTO);
  const place = [contact?.address, contact?.floorInfo].filter(Boolean).join(' ');
  return (
    <section className="home-gallery">
      <div className="wrap">
        <div className="two-col">
          <Link className="photo-panel" to="/board/gallery/jori-center" aria-label="조리읍 행정복지센터 청사 전경">
            {photo === 'ok' ? <img src={BUILDING_PHOTO} alt="" /> : null}
          </Link>
          <div>
            <h2>
              배움이 모이는
              <br />
              조리읍 주민자치센터
            </h2>
            <p>{place ? `${place}에서 만나실 수 있습니다.` : '센터 위치는 확인이 필요합니다.'}</p>
            <div className="button-row">
              <Link className="button secondary" to="/center/facility">
                시설 안내
              </Link>
              <Link className="button secondary" to="/center/contact">
                찾아오시는 길
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function Home() {
  usePageTitle('홈');
  const home = useQuery(homeQuery);

  return (
    <>
      <Hero />
      <EasyStart />
      {home.data?.cycle ? (
        <EasyNotice cycle={home.data.cycle} firstNoticeId={home.data.notices[0]?.postId} />
      ) : null}
      <Intro />
      {home.isPending ? (
        <p className="wrap" role="status">
          센터 소식과 강좌 안내를 불러오는 중입니다.
        </p>
      ) : null}
      {home.isError ? (
        <div className="wrap" role="alert">
          <p>센터 소식과 강좌 안내를 불러오지 못했습니다.</p>
          <button type="button" className="button secondary" onClick={() => void home.refetch()}>
            다시 시도
          </button>
        </div>
      ) : null}
      {home.data ? (
        <>
          <News home={home.data} />
          <CourseGuide home={home.data} />
        </>
      ) : null}
      <Gallery />
    </>
  );
}
