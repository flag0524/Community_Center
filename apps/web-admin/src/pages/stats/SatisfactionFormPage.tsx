// 강좌 만족도 집계자료 등록 화면. 기관이 준 조사 결과의 출처·기간·응답자 수와 문항별 선택 집계를 직접 입력해 검토 전으로 등록한다 (ADM-DSH-002 집계자료)
import type { Schemas } from '@jori/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createSatisfactionSource } from '../../api/satisfactionSources';
import { courseOptionsQuery } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { TableWrap } from '../../components/ListParts';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { RESPONSE_TYPE } from '../../lib/labels';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

type ResponseType = Schemas['ResponseType'];
interface OptionDraft {
  id: string;
  name: string;
  count: string;
  score: string;
}
interface QuestionDraft {
  id: string;
  name: string;
  type: ResponseType;
  respondents: string;
  minScore: string;
  maxScore: string;
  criteria: string;
  options: OptionDraft[];
}

const emptyOption = (): OptionDraft => ({ id: '', name: '', count: '', score: '' });
const emptyQuestion = (): QuestionDraft => ({ id: '', name: '', type: 'SINGLE', respondents: '', minScore: '', maxScore: '', criteria: '', options: [emptyOption()] });
const isCount = (value: string) => /^[0-9]+$/.test(value);
const isScore = (value: string) => /^-?[0-9]+(\.[0-9]{1,6})?$/.test(value);

export function SatisfactionFormPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const courses = useQuery(courseOptionsQuery);
  const [head, setHead] = useState({ courseId: '', provider: '', basisId: '', datasetId: '', periodStart: '', periodEnd: '', respondents: '', criteria: '' });
  const [questions, setQuestions] = useState<QuestionDraft[]>([emptyQuestion()]);
  const [missing, setMissing] = useState<Record<string, string>>({});

  const mutation = useMutation({
    mutationFn: () =>
      createSatisfactionSource(
        {
          courseId: head.courseId,
          provider: head.provider,
          basisId: head.basisId,
          datasetId: head.datasetId,
          periodStart: head.periodStart,
          periodEnd: head.periodEnd,
          respondents: Number(head.respondents),
          criteria: head.criteria,
          questions: questions.map((q) => ({
            questionId: q.id.trim(),
            name: q.name.trim(),
            type: q.type,
            respondents: Number(q.respondents),
            minScore: q.type === 'SCORE' ? q.minScore : null,
            maxScore: q.type === 'SCORE' ? q.maxScore : null,
            criteria: q.criteria.trim(),
            options: q.options.map((o) => ({ optionId: o.id.trim(), name: o.name.trim(), count: Number(o.count), score: q.type === 'SCORE' && o.score !== '' ? o.score : null })),
          })),
        },
        key.current(),
      ),
    onSuccess: (result) => {
      key.renew();
      void queryClient.invalidateQueries({ queryKey: ['satisfaction-sources', 'list'] });
      void navigate(`/satisfaction-sources/${result.sourceId}`, { replace: true });
    },
  });

  const setField = (name: keyof typeof head, value: string) => setHead((current) => ({ ...current, [name]: value }));
  const setQuestion = (index: number, patch: Partial<QuestionDraft>) => setQuestions((current) => current.map((q, at) => (at === index ? { ...q, ...patch } : q)));
  const setOption = (qIndex: number, oIndex: number, patch: Partial<OptionDraft>) =>
    setQuestions((current) => current.map((q, at) => (at === qIndex ? { ...q, options: q.options.map((o, oAt) => (oAt === oIndex ? { ...o, ...patch } : o)) } : q)));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    for (const [name, value] of Object.entries(head)) if (!value.trim()) errors[name] = '필수 항목입니다.';
    if (head.respondents.trim() && !isCount(head.respondents.trim())) errors.respondents = '0 이상의 정수입니다.';
    questions.forEach((q, index) => {
      const at = `questions[${index}]`;
      if (!q.id.trim() || !q.name.trim() || !q.criteria.trim()) errors[at] = '문항 식별자·이름·집계 기준은 필수입니다.';
      else if (!isCount(q.respondents)) errors[at] = '문항 유효응답자 수는 0 이상의 정수입니다.';
      else if (q.type === 'SCORE' && (!isScore(q.minScore) || !isScore(q.maxScore))) errors[at] = '점수 문항은 최소·최대 점수를 숫자로 입력합니다.';
      else if (q.options.some((o) => !o.id.trim() || !o.name.trim())) errors[at] = '선택 항목의 식별자와 이름은 필수입니다.';
      else if (q.options.some((o) => !isCount(o.count))) errors[at] = '선택 응답 수는 0 이상의 정수입니다.';
      else if (q.type === 'SCORE' && q.options.some((o) => o.score !== '' && !isScore(o.score))) errors[at] = '점수는 숫자로 입력하거나 비워 둡니다.';
    });
    setMissing(errors);
    if (Object.keys(errors).length === 0) mutation.mutate();
  };
  const server = fieldErrors(mutation.error);
  const err = (name: string) => missing[name] ?? server[name];
  const questionErrors = questions.map((_, index) => err(`questions[${index}]`)).filter(Boolean);

  const text = (name: keyof typeof head, label: string, hint?: string, type: 'text' | 'date' = 'text') => (
    <Field id={`sat-${name}`} label={label} required error={err(name)} hint={hint}>
      <input {...describe(`sat-${name}`, err(name), hint)} type={type} value={head[name]} onChange={(event) => setField(name, event.target.value)} />
    </Field>
  );

  return (
    <>
      <div className="adm-page-heading">
        <h1>만족도 집계자료 등록</h1>
      </div>
      <p className="adm-notice">기관이 제공한 집계 결과만 입력합니다. 개인 응답은 받지 않습니다. 단일선택·점수 문항은 선택 수의 합이 유효응답자 수와 같아야 하고, 복수선택은 각 선택 수가 유효응답자 수 이하여야 합니다. 무응답·미상 항목도 합계에 넣어 입력하고, 점수가 없는 응답은 점수를 비워 둡니다.</p>
      <form className="adm-form" aria-label="만족도 집계자료" noValidate onSubmit={submit}>
        <div className="adm-form-grid">
          <Field id="sat-courseId" label="강좌" required error={err('courseId')} hint={courses.isError ? '강좌 목록을 불러오지 못했습니다.' : undefined}>
            <select {...describe('sat-courseId', err('courseId'))} value={head.courseId} onChange={(event) => setField('courseId', event.target.value)}>
              <option value="">선택</option>
              {(courses.data?.courses ?? []).map((course) => (
                <option key={course.id} value={course.id}>
                  {course.name}
                </option>
              ))}
            </select>
          </Field>
          {text('provider', '출처 기관')}
          {text('basisId', '근거 식별자', '문서번호 등 출처를 찾을 수 있는 값입니다.')}
          {text('datasetId', '계열 키', '같은 강좌·자료의 새 버전은 같은 계열 키로 등록합니다.')}
          {text('periodStart', '조사 기간 시작', undefined, 'date')}
          {text('periodEnd', '조사 기간 끝', undefined, 'date')}
          {text('respondents', '전체 응답자 수')}
          <Field id="sat-criteria" label="집계 기준" required full error={err('criteria')} hint="모집단·중복 제거·무응답·복수선택·점수 산식·원자료 범위">
            <textarea {...describe('sat-criteria', err('criteria'), '모집단·중복 제거·무응답·복수선택·점수 산식·원자료 범위')} rows={3} value={head.criteria} onChange={(event) => setField('criteria', event.target.value)} />
          </Field>
        </div>

        {questions.map((question, qIndex) => {
          const n = qIndex + 1;
          const qInput = (name: 'id' | 'name' | 'respondents' | 'minScore' | 'maxScore' | 'criteria', label: string) => (
            <label className="wide">
              {n}번 문항 {label}
              <input aria-label={`${n}번 문항 ${label}`} value={question[name]} onChange={(event) => setQuestion(qIndex, { [name]: event.target.value })} />
            </label>
          );
          return (
            <fieldset key={qIndex} className="adm-fieldset">
              <legend>{n}번 문항</legend>
              <div className="adm-form-grid">
                {qInput('id', '식별자')}
                {qInput('name', '이름')}
                <label>
                  {n}번 문항 유형
                  <select aria-label={`${n}번 문항 유형`} value={question.type} onChange={(event) => setQuestion(qIndex, { type: event.target.value as ResponseType })}>
                    {Object.entries(RESPONSE_TYPE).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                {qInput('respondents', '유효응답자 수')}
                {question.type === 'SCORE' && (
                  <>
                    {qInput('minScore', '최소 점수')}
                    {qInput('maxScore', '최대 점수')}
                  </>
                )}
                {qInput('criteria', '집계 기준')}
              </div>
              <TableOptions
                question={question}
                n={n}
                onChange={(oIndex, patch) => setOption(qIndex, oIndex, patch)}
                onAdd={() => setQuestion(qIndex, { options: [...question.options, emptyOption()] })}
                onRemove={(oIndex) => setQuestion(qIndex, { options: question.options.filter((_, at) => at !== oIndex) })}
              />
              <div className="adm-actions">
                <button type="button" className="adm-button secondary" disabled={questions.length === 1} onClick={() => setQuestions((current) => current.filter((_, at) => at !== qIndex))}>
                  {n}번 문항 삭제
                </button>
              </div>
            </fieldset>
          );
        })}
        {questionErrors.map((message) => (
          <p key={message} className="adm-field-error" role="alert">
            {message}
          </p>
        ))}
        <div className="adm-actions">
          <button type="button" className="adm-button secondary" onClick={() => setQuestions((current) => [...current, emptyQuestion()])}>
            문항 추가
          </button>
        </div>

        {mutation.isError && Object.keys(server).length === 0 && (
          <p className="adm-message error" role="alert">
            {errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          <button type="submit" className="adm-button" disabled={mutation.isPending}>
            등록
          </button>
          <Link className="adm-button secondary" to="/satisfaction-sources">
            취소
          </Link>
        </div>
      </form>
    </>
  );
}

interface TableOptionsProps {
  question: QuestionDraft;
  n: number;
  onChange: (index: number, patch: Partial<OptionDraft>) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}

function TableOptions({ question, n, onChange, onAdd, onRemove }: TableOptionsProps) {
  return (
    <>
      <TableWrap label={`${n}번 문항 선택 항목 표`}>
      <table>
        <thead>
          <tr>
            <th scope="col">선택 식별자</th>
            <th scope="col">선택 이름</th>
            <th scope="col">응답 수</th>
            {question.type === 'SCORE' && <th scope="col">점수</th>}
            <th scope="col">항목 관리</th>
          </tr>
        </thead>
        <tbody>
          {question.options.map((option, oIndex) => {
            const m = oIndex + 1;
            const input = (name: keyof OptionDraft, label: string) => <input aria-label={`${n}번 문항 ${m}번 선택 ${label}`} value={option[name]} onChange={(event) => onChange(oIndex, { [name]: event.target.value })} />;
            return (
              <tr key={oIndex}>
                <td>{input('id', '식별자')}</td>
                <td>{input('name', '이름')}</td>
                <td>{input('count', '응답 수')}</td>
                {question.type === 'SCORE' && <td>{input('score', '점수')}</td>}
                <td>
                  <button type="button" className="adm-button secondary" disabled={question.options.length === 1} onClick={() => onRemove(oIndex)}>
                    {n}번 문항 {m}번 선택 삭제
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </TableWrap>
      <div className="adm-actions">
        <button type="button" className="adm-button secondary" onClick={onAdd}>
          {n}번 문항 선택 항목 추가
        </button>
      </div>
    </>
  );
}
