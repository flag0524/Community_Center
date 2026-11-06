// 문의·답변 상세 화면. 문의 본문을 읽고 한 단계 답변을 쓰거나 고친다. 고치면 이력이 남고 비공개 범위는 답변에도 그대로 적용된다 (ADM-MBR-003P)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { answerInquiry } from '../../api/inquiries';
import { adminInquiryQuery, type AdminInquiry } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { TableWrap } from '../../components/ListParts';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { kstDateTime } from '../../lib/format';
import { ANSWER_ACTION, INQUIRY_STATUS } from '../../lib/labels';
import { isVersionConflict } from '../../lib/messages';

export function InquiryDetailPage() {
  const { inquiryId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(adminInquiryQuery(inquiryId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return <InquiryDetail key={data.inquiryId} inquiry={data} />;
}

function InquiryDetail({ inquiry }: { inquiry: AdminInquiry }) {
  const queryClient = useQueryClient();
  const [content, setContent] = useState(inquiry.answer?.content ?? '');
  const [link, setLink] = useState(inquiry.answer?.relatedLink ?? '');
  const [missing, setMissing] = useState('');
  const [saved, setSaved] = useState(false);

  const mutation = useMutation({
    mutationFn: () => answerInquiry(inquiry.inquiryId, content.trim(), link.trim() || null, inquiry.answer?.version ?? 0),
    onSuccess: (result) => {
      queryClient.setQueryData(adminInquiryQuery(result.inquiryId).queryKey, result);
      queryClient.removeQueries({ queryKey: ['inquiries', 'list'] });
      setSaved(true);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!content.trim()) return setMissing('답변 내용을 입력해 주세요.');
    setMissing('');
    mutation.mutate();
  };
  const server = fieldErrors(mutation.error);

  return (
    <>
      <div className="adm-page-heading">
        <h1>문의 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>제목</dt>
        <dd>{inquiry.title}</dd>
        <dt>분류</dt>
        <dd>{inquiry.categoryName}</dd>
        <dt>작성자</dt>
        <dd>{inquiry.authorName}</dd>
        <dt>공개</dt>
        <dd>{inquiry.isPrivate ? '비공개' : '공개'}</dd>
        <dt>접수일</dt>
        <dd>{inquiry.receivedOn}</dd>
        <dt>답변상태</dt>
        <dd>{INQUIRY_STATUS[inquiry.status]}</dd>
        <dt>문의 내용</dt>
        <dd className="adm-pre">{inquiry.content}</dd>
      </dl>
      {inquiry.isPrivate && <p className="adm-notice">비공개 문의입니다. 이 문의의 공개 범위는 답변에도 그대로 적용됩니다.</p>}

      <h2 className="adm-section">답변</h2>
      {inquiry.answer && (
        <p className="adm-state">
          {inquiry.answer.answeredBy} · {kstDateTime(inquiry.answer.answeredAt)}
        </p>
      )}
      <form className="adm-form" aria-label="답변" noValidate onSubmit={submit}>
        <fieldset disabled={!inquiry.canAnswer}>
          <div className="adm-form-grid">
            <Field id="answer-content" label="답변 내용" required error={missing || server.content} full>
              <textarea
                {...describe('answer-content', missing || server.content)}
                rows={6}
                maxLength={4000}
                value={content}
                onChange={(event) => {
                  setSaved(false);
                  setContent(event.target.value);
                }}
              />
            </Field>
            <Field id="answer-link" label="관련 화면 링크" error={server.relatedLink} hint="사이트 안 경로(/로 시작)나 https 주소를 입력합니다." full>
              <input
                {...describe('answer-link', server.relatedLink, '사이트 안 경로(/로 시작)나 https 주소를 입력합니다.')}
                value={link}
                maxLength={300}
                onChange={(event) => {
                  setSaved(false);
                  setLink(event.target.value);
                }}
              />
            </Field>
          </div>
        </fieldset>
        <p className="adm-notice">답변은 문의 하나에 한 번만 달 수 있습니다. 고치면 수정 이력이 남습니다.</p>
        {saved && (
          <p className="adm-message" role="status">
            저장했습니다.
          </p>
        )}
        {mutation.isError && Object.keys(server).length === 0 && (
          <p className="adm-message error" role="alert">
            {isVersionConflict(mutation.error) ? '다른 곳에서 먼저 답변되었습니다. 목록에서 다시 열어 주세요.' : errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          {inquiry.canAnswer && (
            <button className="adm-button" type="submit" disabled={mutation.isPending}>
              {inquiry.answer ? '답변 수정' : '답변 등록'}
            </button>
          )}
          <Link className="adm-button secondary" to="/mbr/inquiries">
            목록
          </Link>
        </div>
      </form>

      <h2 className="adm-section">답변 이력</h2>
      {inquiry.history.length > 0 ? (
        <TableWrap label="답변 이력">
          <table>
            <thead>
              <tr>
                <th scope="col">시각</th>
                <th scope="col">처리</th>
                <th scope="col">담당자</th>
              </tr>
            </thead>
            <tbody>
              {inquiry.history.map((entry) => (
                <tr key={`${entry.at}-${entry.action}`}>
                  <td>{kstDateTime(entry.at)}</td>
                  <td>{ANSWER_ACTION[entry.action]}</td>
                  <td>{entry.by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>답변 이력이 없습니다.</p>
      )}
    </>
  );
}
