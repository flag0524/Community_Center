// 쉬운 화면의 전화 도움 안내와 개인정보처리방침·주소·전화가 있는 바닥글
import { Link } from 'react-router-dom';
import { PhoneLink } from '../components/PhoneLink';
import { FOOTER_LINKS } from './navigation';
import { useContact } from './useContact';

export function EasyHelp() {
  const contact = useContact();
  return (
    <aside className="easy-only easy-help" aria-label="도움 안내">
      <div className="wrap">
        <div>
          <strong>혼자 이용하기 어려우신가요?</strong>
          <p>센터에 전화해 궁금한 점을 물어보세요.</p>
        </div>
        {contact?.phone ? (
          <a href={`tel:${contact.phone}`}>전화 문의　{contact.phone}</a>
        ) : (
          <span>전화 번호 확인 필요</span>
        )}
      </div>
    </aside>
  );
}

export function Footer() {
  const contact = useContact();
  // 시안은 도로명 주소와 층 안내 사이를 전각 공백 하나로 띄운다.
  const street = [contact?.postalCode ? `[${contact.postalCode}]` : null, contact?.address].filter(Boolean).join(' ');
  const address = [street, contact?.floorInfo].filter(Boolean).join('　');

  return (
    <footer className="footer">
      <div className="wrap">
        <div className="footer-top">
          <strong>조리읍주민자치센터</strong>
          <div className="footer-links">
            {FOOTER_LINKS.map((item) => (
              <Link key={item.to} to={item.to}>
                {item.label}
              </Link>
            ))}
          </div>
        </div>
        <div className="footer-bottom">
          <div>
            <p>{address || '주소 확인 필요'}</p>
            <p>
              전화 <PhoneLink number={contact?.phone} />　 |　 행정복지센터 대표{' '}
              <PhoneLink number={contact?.adminOfficePhone} />
            </p>
          </div>
          <a href="#top">맨 위로 ↑</a>
        </div>
      </div>
    </footer>
  );
}
