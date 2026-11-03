// 서버가 준 안내·센터소개 문서를 절 단위로 그린다. 문안은 화면 코드에 두지 않는다
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { contentQuery, type ContentDocument, type ContentSlug } from '../../api/queries';
import { QueryFallback } from '../../components/QueryFallback';
import { NAV_GROUPS } from '../../layout/navigation';
import { SubLayout } from '../../layout/SubLayout';
import { usePageTitle } from '../../lib/usePageTitle';

type Section = ContentDocument['sections'][number];

function ContentLink({ label, url }: { label: string; url: string }) {
  // 사이트 안 경로만 앱 안에서 이동한다. 전화 걸기와 바깥 주소는 그대로 연다.
  return url.startsWith('/') ? (
    <Link to={url}>{label}</Link>
  ) : (
    <a href={url} rel="noopener noreferrer">
      {label}
    </a>
  );
}

function SectionBody({ section }: { section: Section }) {
  return (
    <>
      {section.paragraphs.map((text) => (
        <p key={text}>{text}</p>
      ))}
      {section.steps.length > 0 ? (
        <ol className="steps" aria-label={`${section.heading} 단계`}>
          {section.steps.map((step) => (
            <li key={step.title}>
              <strong>{step.title}</strong>
              <p>{step.body}</p>
            </li>
          ))}
        </ol>
      ) : null}
      {section.items.length > 0 ? (
        <ul>
          {section.items.map((item) => (
            <li key={`${item.label}${item.text}`}>
              {item.label ? <b>{item.label}</b> : null} {item.text}
            </li>
          ))}
        </ul>
      ) : null}
      {section.table ? (
        <div className="table-wrap">
          <table aria-label={`${section.heading} 표`}>
            <thead>
              <tr>
                {section.table.columns.map((column) => (
                  <th key={column} scope="col">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {section.table.rows.map((row) => (
                <tr key={row.join('|')}>
                  {row.map((cell, index) => (
                    <td key={`${index}${cell}`}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {section.links.map((link) => (
        <p key={link.url}>
          <ContentLink {...link} />
        </p>
      ))}
    </>
  );
}

export function ContentPage({ slug, groupTitle }: { slug: ContentSlug; groupTitle: string }) {
  const query = useQuery(contentQuery(slug));
  const document = query.data;
  usePageTitle(document?.title ?? '안내');
  const group = NAV_GROUPS.find((item) => item.title === groupTitle)!;

  if (!document) return <QueryFallback query={query} what="안내 문서" />;

  return (
    <SubLayout
      group={group}
      title={document.title}
      subtitle={document.subtitle ?? ''}
      crumbs={[{ label: group.title }, { label: document.title }]}
    >
      {document.sections.map((section) =>
        // 항목(날짜 + 내용)이 있는 절은 연혁처럼 연도별 소제목으로, 나머지는 일반 절로 그린다.
        section.items.length > 0 ? (
          <div className="timeline" key={section.heading}>
            <section>
              <h3>{section.heading}</h3>
              <SectionBody section={section} />
            </section>
          </div>
        ) : (
          <section className="article-text" key={section.heading}>
            <h2 className="section-heading">{section.heading}</h2>
            <SectionBody section={section} />
          </section>
        ),
      )}
    </SubLayout>
  );
}