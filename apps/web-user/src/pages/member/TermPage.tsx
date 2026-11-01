// 이용약관·개인정보처리방침·이메일무단수집거부. 서버 문서의 본문을 소제목과 문단으로 그린다
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { termQuery, type TermType } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';
import { NotFound } from '../Placeholder';

// 주소에 쓰는 이름과 서버의 약관 유형 대응
const TERM_BY_SLUG: Record<string, TermType> = {
  'terms-of-use': 'TERMS_OF_USE',
  'privacy-policy': 'PRIVACY_POLICY',
  'email-refusal': 'EMAIL_REFUSAL',
};

/** 본문은 빈 줄로 문단을 나누고 `## `로 시작하는 문단은 소제목이다. 소제목 하나가 section 하나가 된다. */
function TermBody({ body }: { body: string }) {
  const sections: Array<{ heading: string | null; paragraphs: string[] }> = [];
  for (const block of body.split(/\n{2,}/).map((text) => text.trim()).filter(Boolean)) {
    if (block.startsWith('## ')) sections.push({ heading: block.slice(3).trim(), paragraphs: [] });
    else {
      if (sections.length === 0) sections.push({ heading: null, paragraphs: [] });
      sections.at(-1)!.paragraphs.push(block);
    }
  }
  return (
    <div className="article-text">
      {sections.map((section, index) => (
        <section key={index}>
          {section.heading ? <h2>{section.heading}</h2> : null}
          {section.paragraphs.map((text, at) => (
            <p key={at}>{text}</p>
          ))}
        </section>
      ))}
    </div>
  );
}

export function TermPage() {
  const { slug = '' } = useParams();
  const termType = TERM_BY_SLUG[slug];
  const query = useQuery({ ...termQuery(termType ?? 'TERMS_OF_USE'), enabled: termType !== undefined });
  const term = query.data;
  usePageTitle(term?.title ?? '약관');

  if (termType === undefined) return <NotFound />;
  if (!term) return <QueryFallback query={query} what="약관" />;

  return (
    <ServicePage title={term.title} crumbs={[{ label: '회원서비스' }, { label: term.title }]}>
      <div className="proto">
        <TermBody body={term.body} />
      </div>
    </ServicePage>
  );
}
