// 홈·센터 콘텐츠 등록·수정 화면. 연락처 유형은 본문 대신 구조 입력을 받고 비주얼·배너·팝업은 저장한 뒤 이미지를 올린다 (ADM-MBR-004P)
import type { Schemas } from '@jori/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { createContent, updateContent, type AdminContent, type AdminContentWrite, type ContactFields } from '../../api/contents';
import { adminContentQuery } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { OwnerFiles } from '../../components/OwnerFiles';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { fromDateTimeInput, toDateTimeInput } from '../../lib/format';
import { CONTENT_TYPE } from '../../lib/labels';
import { isVersionConflict } from '../../lib/messages';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

type ContentType = Schemas['ContentType'];
const TYPES = Object.keys(CONTENT_TYPE) as ContentType[];
const IMAGE_TYPES: ContentType[] = ['VISUAL', 'BANNER', 'POPUP'];
const CONTACT_LABELS: Array<[keyof ContactFields, string]> = [
  ['phone', '수강문의 번호'],
  ['adminOfficePhone', '행정복지센터 대표번호'],
  ['postalCode', '우편번호'],
  ['address', '주소'],
  ['floorInfo', '층·위치 안내'],
  ['openHours', '운영시간'],
  ['parking', '주차 안내'],
];

interface Values {
  contentType: ContentType;
  title: string;
  body: string;
  url: string;
  periodStart: string;
  periodEnd: string;
  posted: boolean;
  sortSeq: string;
  contact: Record<keyof ContactFields, string>;
}

const blankContact = (): Values['contact'] => ({ phone: '', adminOfficePhone: '', postalCode: '', address: '', floorInfo: '', openHours: '', parking: '' });

const fromContent = (content: AdminContent): Values => ({
  contentType: content.contentType,
  title: content.title,
  body: content.body,
  url: content.url ?? '',
  periodStart: content.periodStart ? toDateTimeInput(content.periodStart) : '',
  periodEnd: content.periodEnd ? toDateTimeInput(content.periodEnd) : '',
  posted: content.posted,
  sortSeq: String(content.sortSeq),
  contact: { ...blankContact(), ...Object.fromEntries(Object.entries(content.contact ?? {}).map(([key, value]) => [key, value ?? ''])) },
});

export function ContentFormPage({ mode }: { mode: 'create' | 'edit' }) {
  const { contentId = '' } = useParams();
  const [params] = useSearchParams();
  const { data, isPending, isError, error } = useQuery({ ...adminContentQuery(contentId), enabled: mode === 'edit' });
  if (mode === 'edit') {
    if (isPending) return <p role="status">불러오는 중입니다.</p>;
    if (isError) return <p role="alert">{errorMessage(error)}</p>;
    return <ContentForm key={data.contentId} content={data} />;
  }
  const requested = params.get('type') as ContentType | null;
  return <ContentForm key="new" initialType={requested && TYPES.includes(requested) ? requested : TYPES[0]!} />;
}

function ContentForm({ content, initialType }: { content?: AdminContent; initialType?: ContentType }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const [values, setValues] = useState<Values>(
    content ? fromContent(content) : { contentType: initialType ?? 'VISUAL', title: '', body: '', url: '', periodStart: '', periodEnd: '', posted: false, sortSeq: '0', contact: blankContact() },
  );
  const [missing, setMissing] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const isContact = values.contentType === 'CONTACT';

  const body = (): AdminContentWrite => ({
    contentType: values.contentType,
    title: values.title.trim(),
    body: isContact ? '' : values.body,
    url: values.url.trim() || null,
    periodStart: values.periodStart ? fromDateTimeInput(values.periodStart) : null,
    periodEnd: values.periodEnd ? fromDateTimeInput(values.periodEnd) : null,
    posted: values.posted,
    sortSeq: Number(values.sortSeq),
    contact: isContact ? Object.fromEntries(Object.entries(values.contact).map(([name, value]) => [name, value.trim() || null])) : null,
  });

  const mutation = useMutation({
    mutationFn: () => (content ? updateContent(content.contentId, body(), content.version) : createContent(body(), key.current())),
    onSuccess: (result) => {
      key.renew();
      // 같은 화면이 읽는 캐시는 지우지 않고 다시 읽게만 한다. 지우면 화면이 불러오는 중으로 돌아가 저장 안내가 사라진다.
      void queryClient.invalidateQueries({ queryKey: ['contents', 'list'] });
      if (content) {
        queryClient.setQueryData(adminContentQuery(result.contentId).queryKey, result);
        setSaved(true);
      } else void navigate(`/mbr/contents/${result.contentId}`, { replace: true });
    },
  });

  const set = <K extends keyof Values>(name: K, value: Values[K]) => {
    setSaved(false);
    setValues((current) => ({ ...current, [name]: value }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!values.title.trim()) errors.title = '필수 항목입니다.';
    if (!isContact && !values.body.trim()) errors.body = '필수 항목입니다.';
    if (!(Number(values.sortSeq) >= 0)) errors.sortSeq = '0 이상의 숫자를 입력해 주세요.';
    setMissing(errors);
    if (Object.keys(errors).length === 0) mutation.mutate();
  };

  const server = fieldErrors(mutation.error);
  const err = (name: string) => missing[name] ?? server[name];

  return (
    <>
      <div className="adm-page-heading">
        <h1>{content ? '콘텐츠 수정' : '콘텐츠 등록'}</h1>
      </div>
      <form className="adm-form" aria-label="콘텐츠" noValidate onSubmit={submit}>
        <div className="adm-form-grid">
          <Field id="content-type" label="유형" required error={err('contentType')}>
            <select {...describe('content-type', err('contentType'))} value={values.contentType} disabled={content !== undefined} onChange={(event) => set('contentType', event.target.value as ContentType)}>
              {TYPES.map((value) => (
                <option key={value} value={value}>
                  {CONTENT_TYPE[value]}
                </option>
              ))}
            </select>
          </Field>
          <Field id="content-sort" label="정렬 순서" error={err('sortSeq')}>
            <input {...describe('content-sort', err('sortSeq'))} type="number" min={0} value={values.sortSeq} onChange={(event) => set('sortSeq', event.target.value)} />
          </Field>
          <Field id="content-title" label="제목" required error={err('title')} full>
            <input {...describe('content-title', err('title'))} value={values.title} maxLength={256} onChange={(event) => set('title', event.target.value)} />
          </Field>
          {isContact ? (
            CONTACT_LABELS.map(([name, label]) => (
              <Field key={name} id={`contact-${name}`} label={label} error={err('contact')}>
                <input
                  {...describe(`contact-${name}`)}
                  value={values.contact[name]}
                  maxLength={200}
                  onChange={(event) => {
                    setSaved(false);
                    setValues((current) => ({ ...current, contact: { ...current.contact, [name]: event.target.value } }));
                  }}
                />
              </Field>
            ))
          ) : (
            <Field id="content-body" label="본문" required error={err('body')} full>
              <textarea {...describe('content-body', err('body'))} rows={8} maxLength={20000} value={values.body} onChange={(event) => set('body', event.target.value)} />
            </Field>
          )}
          <Field id="content-url" label="링크" error={err('url')} hint="사이트 안 경로(/로 시작)나 https 주소를 입력합니다." full>
            <input {...describe('content-url', err('url'), '사이트 안 경로(/로 시작)나 https 주소를 입력합니다.')} value={values.url} maxLength={2000} onChange={(event) => set('url', event.target.value)} />
          </Field>
          <Field id="content-start" label="게시 시작" error={err('periodStart')} hint="비우면 바로 게시합니다.">
            <input {...describe('content-start', err('periodStart'), '비우면 바로 게시합니다.')} type="datetime-local" value={values.periodStart} onChange={(event) => set('periodStart', event.target.value)} />
          </Field>
          <Field id="content-end" label="게시 종료" error={err('periodEnd')} hint="비우면 계속 게시합니다.">
            <input {...describe('content-end', err('periodEnd'), '비우면 계속 게시합니다.')} type="datetime-local" value={values.periodEnd} onChange={(event) => set('periodEnd', event.target.value)} />
          </Field>
          <Field id="content-posted" label="게시 여부">
            <input {...describe('content-posted')} type="checkbox" checked={values.posted} onChange={(event) => set('posted', event.target.checked)} />
          </Field>
        </div>
        {saved && (
          <p className="adm-message" role="status">
            저장했습니다.
          </p>
        )}
        {mutation.isError && Object.keys(server).length === 0 && (
          <p className="adm-message error" role="alert">
            {isVersionConflict(mutation.error) ? '다른 곳에서 먼저 수정되었습니다. 목록에서 다시 열어 주세요.' : errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          <button className="adm-button" type="submit" disabled={mutation.isPending}>
            저장
          </button>
          <Link className="adm-button secondary" to={`/mbr/contents?type=${values.contentType}`}>
            목록
          </Link>
        </div>
      </form>
      {IMAGE_TYPES.includes(values.contentType) &&
        (content ? <OwnerFiles ownerPath={`/contents/${content.contentId}`} label="이미지" /> : <p className="adm-notice">이미지는 콘텐츠를 저장한 뒤에 추가할 수 있습니다.</p>)}
    </>
  );
}
