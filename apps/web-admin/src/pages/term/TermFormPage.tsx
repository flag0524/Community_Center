// 약관·동의문 버전 작성·상세 화면. 검토 상태만 고칠 수 있고 확정하면 문안 해시가 고정되며 게시된 문안은 새 버전으로 개정한다 (ADM-MBR-005P)
import type { Schemas } from '@jori/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { createTermVersion, fixTermVersion, publishTermVersion, updateTermVersion, type TermVersion } from '../../api/terms';
import { termVersionQuery } from '../../api/queries';
import { ConfirmButton } from '../../components/ConfirmButton';
import { Field, describe } from '../../components/Field';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { TERM_STATUS, TERM_TYPE } from '../../lib/labels';
import { isVersionConflict } from '../../lib/messages';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

type TermType = Schemas['TermType'];
const TYPES = Object.keys(TERM_TYPE) as TermType[];

interface Values {
  versionName: string;
  effectiveOn: string;
  essential: boolean;
  body: string;
}

export function TermFormPage({ mode }: { mode: 'create' | 'edit' }) {
  const { versionId = '' } = useParams();
  const [params] = useSearchParams();
  const base = params.get('base') ?? '';
  const detail = useQuery({ ...termVersionQuery(mode === 'edit' ? versionId : base), enabled: mode === 'edit' || base !== '' });
  if (mode === 'edit') {
    if (detail.isPending) return <p role="status">불러오는 중입니다.</p>;
    if (detail.isError) return <p role="alert">{errorMessage(detail.error)}</p>;
    return <TermView key={detail.data.versionId} term={detail.data} />;
  }
  const requested = params.get('type') as TermType | null;
  const type = requested && TYPES.includes(requested) ? requested : TYPES[0]!;
  if (base && detail.isPending) return <p role="status">불러오는 중입니다.</p>;
  if (base && detail.isError) return <p role="alert">{errorMessage(detail.error)}</p>;
  return <TermCreate key={`${type}-${base}`} type={type} base={detail.data} />;
}

function TermCreate({ type, base }: { type: TermType; base?: TermVersion }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const [values, setValues] = useState<Values>({ versionName: '', effectiveOn: '', essential: base?.essential ?? true, body: base?.body ?? '' });
  const [missing, setMissing] = useState<Record<string, string>>({});

  const mutation = useMutation({
    mutationFn: () => createTermVersion(type, { versionName: values.versionName.trim(), effectiveOn: values.effectiveOn, essential: values.essential, body: values.body, baseVersionId: base?.versionId ?? null }, key.current()),
    onSuccess: (result) => {
      key.renew();
      void queryClient.invalidateQueries({ queryKey: ['terms', 'list'] });
      void navigate(`/mbr/terms/${result.versionId}`, { replace: true });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!values.versionName.trim()) errors.versionName = '필수 항목입니다.';
    if (!values.effectiveOn) errors.effectiveOn = '필수 항목입니다.';
    if (!values.body.trim()) errors.body = '필수 항목입니다.';
    setMissing(errors);
    if (Object.keys(errors).length === 0) mutation.mutate();
  };
  const server = fieldErrors(mutation.error);
  const err = (name: string) => missing[name] ?? server[name];

  return (
    <>
      <div className="adm-page-heading">
        <h1>새 버전 작성</h1>
      </div>
      <p className="adm-state">{TERM_TYPE[type]}</p>
      {base && <p className="adm-notice">이전 버전 {base.versionName}의 문안을 복사했습니다. 고쳐서 저장하면 검토 상태의 새 버전이 됩니다.</p>}
      <form className="adm-form" aria-label="약관 버전" noValidate onSubmit={submit}>
        <TermFields values={values} setValues={setValues} err={err} />
        {mutation.isError && Object.keys(server).length === 0 && (
          <p className="adm-message error" role="alert">
            {errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          <button className="adm-button" type="submit" disabled={mutation.isPending}>
            저장
          </button>
          <Link className="adm-button secondary" to={`/mbr/terms?type=${type}`}>
            목록
          </Link>
        </div>
      </form>
    </>
  );
}

function TermFields({ values, setValues, err, locked }: { values: Values; setValues: (update: (current: Values) => Values) => void; err: (name: string) => string | undefined; locked?: boolean }) {
  const set = <K extends keyof Values>(name: K, value: Values[K]) => setValues((current) => ({ ...current, [name]: value }));
  return (
    <fieldset disabled={locked}>
      <div className="adm-form-grid">
        <Field id="term-name" label="버전 이름" required error={err('versionName')}>
          <input {...describe('term-name', err('versionName'))} value={values.versionName} maxLength={40} onChange={(event) => set('versionName', event.target.value)} />
        </Field>
        <Field id="term-effective" label="시행일" required error={err('effectiveOn')}>
          <input {...describe('term-effective', err('effectiveOn'))} type="date" value={values.effectiveOn} onChange={(event) => set('effectiveOn', event.target.value)} />
        </Field>
        <Field id="term-essential" label="필수 동의">
          <input {...describe('term-essential')} type="checkbox" checked={values.essential} onChange={(event) => set('essential', event.target.checked)} />
        </Field>
        <Field id="term-body" label="문안" required error={err('body')} full>
          <textarea {...describe('term-body', err('body'))} rows={14} maxLength={50000} value={values.body} onChange={(event) => set('body', event.target.value)} />
        </Field>
      </div>
    </fieldset>
  );
}

function TermView({ term }: { term: TermVersion }) {
  const queryClient = useQueryClient();
  const initial: Values = { versionName: term.versionName, effectiveOn: term.effectiveOn, essential: term.essential, body: term.body };
  const [values, setValues] = useState<Values>(initial);
  const [missing, setMissing] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const dirty = values.versionName !== term.versionName || values.effectiveOn !== term.effectiveOn || values.essential !== term.essential || values.body !== term.body;

  const done = (text: string) => (result: TermVersion) => {
    queryClient.setQueryData(termVersionQuery(result.versionId).queryKey, result);
    void queryClient.invalidateQueries({ queryKey: ['terms', 'list'] });
    setMessage(text);
  };
  const save = useMutation({
    mutationFn: () => updateTermVersion(term.versionId, { versionName: values.versionName.trim(), effectiveOn: values.effectiveOn, essential: values.essential, body: values.body }, term.version),
    onSuccess: done('저장했습니다.'),
  });
  const fix = useMutation({ mutationFn: () => fixTermVersion(term.versionId, term.version), onSuccess: done('확정했습니다. 문안 해시가 고정되었습니다.') });
  const publish = useMutation({ mutationFn: () => publishTermVersion(term.versionId, term.version), onSuccess: done('게시했습니다.') });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!values.versionName.trim()) errors.versionName = '필수 항목입니다.';
    if (!values.effectiveOn) errors.effectiveOn = '필수 항목입니다.';
    if (!values.body.trim()) errors.body = '필수 항목입니다.';
    setMissing(errors);
    setMessage('');
    if (Object.keys(errors).length === 0) save.mutate();
  };
  const server = fieldErrors(save.error);
  const err = (name: string) => missing[name] ?? server[name];
  const failed = [save, fix, publish].find((mutation) => mutation.isError && Object.keys(fieldErrors(mutation.error)).length === 0)?.error;
  const retired = term.status === 'PUBLISHED' || term.status === 'ENDED';

  return (
    <>
      <div className="adm-page-heading">
        <h1>약관 버전</h1>
      </div>
      <dl className="adm-facts">
        <dt>종류</dt>
        <dd>{TERM_TYPE[term.termType]}</dd>
        <dt>상태</dt>
        <dd>{TERM_STATUS[term.status]}</dd>
        <dt>게시일</dt>
        <dd>{term.postedOn ?? '-'}</dd>
        <dt>동의 회원 수</dt>
        <dd>{term.agreedCount.toLocaleString('ko-KR')}명</dd>
        <dt>문안 해시</dt>
        <dd className="adm-pre">{term.contentHash ?? '확정하면 고정됩니다.'}</dd>
      </dl>
      {retired && <p className="adm-notice">게시된 문안은 고칠 수 없습니다. 고치려면 새 버전으로 개정해 주세요.</p>}
      {term.status === 'FIXED' && <p className="adm-notice">확정된 문안은 고칠 수 없습니다. 게시하면 시행일 이후 신규 가입·재동의 시점에 적용됩니다.</p>}
      <form className="adm-form" aria-label="약관 버전" noValidate onSubmit={submit}>
        <TermFields values={values} setValues={setValues} err={err} locked={!term.canEdit} />
        {message && (
          <p className="adm-message" role="status">
            {message}
          </p>
        )}
        {failed && (
          <p className="adm-message error" role="alert">
            {isVersionConflict(failed) ? '다른 곳에서 먼저 바뀌었습니다. 목록에서 다시 열어 주세요.' : errorMessage(failed)}
          </p>
        )}
        {dirty && term.canFix && <p className="adm-notice">고친 내용을 저장한 뒤에 확정할 수 있습니다.</p>}
        <div className="adm-actions">
          {term.canEdit && (
            <button className="adm-button" type="submit" disabled={save.isPending}>
              저장
            </button>
          )}
          {term.canFix && <ConfirmButton label="확정" confirmLabel="정말 확정" target={term.versionName} disabled={dirty || fix.isPending} onConfirm={() => fix.mutate()} />}
          {term.canPublish && <ConfirmButton label="게시" confirmLabel="정말 게시" target={term.versionName} disabled={publish.isPending} onConfirm={() => publish.mutate()} />}
          {retired && (
            <Link className="adm-button" to={`/mbr/terms/new?type=${term.termType}&base=${term.versionId}`}>
              새 버전으로 개정
            </Link>
          )}
          <Link className="adm-button secondary" to={`/mbr/terms?type=${term.termType}`}>
            목록
          </Link>
        </div>
      </form>
    </>
  );
}