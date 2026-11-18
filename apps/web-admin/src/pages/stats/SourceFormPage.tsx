// 연령·성별 집계자료 등록 화면. 기관이 준 출처·기간·기준일과 연령구간×성별 인원표를 직접 입력해 검토 대기로 등록한다 (ADM-DSH-002 집계자료)
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createSource } from '../../api/statsSources';
import { TableWrap } from '../../components/ListParts';
import { Field, describe } from '../../components/Field';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

interface RowDraft {
  ageGroupId: string;
  ageGroupName: string;
  lowerAge: string;
  upperAge: string;
  genderId: string;
  genderName: string;
  count: string;
}

const emptyRow = (): RowDraft => ({ ageGroupId: '', ageGroupName: '', lowerAge: '', upperAge: '', genderId: '', genderName: '', count: '' });
const isCount = (value: string) => /^[0-9]+$/.test(value);
const isAge = (value: string) => value === '' || /^[0-9]{1,3}$/.test(value);

export function SourceFormPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const [head, setHead] = useState({ provider: '', basisId: '', datasetId: '', periodStart: '', periodEnd: '', ageBasisDate: '', dedupeNote: '' });
  const [rows, setRows] = useState<RowDraft[]>([emptyRow()]);
  const [missing, setMissing] = useState<Record<string, string>>({});

  const mutation = useMutation({
    mutationFn: () =>
      createSource(
        {
          ...head,
          rows: rows.map((row) => ({
            ageGroupId: row.ageGroupId.trim(),
            ageGroupName: row.ageGroupName.trim(),
            lowerAge: row.lowerAge === '' ? null : Number(row.lowerAge),
            upperAge: row.upperAge === '' ? null : Number(row.upperAge),
            genderId: row.genderId.trim(),
            genderName: row.genderName.trim(),
            count: Number(row.count),
          })),
        },
        key.current(),
      ),
    onSuccess: (result) => {
      key.renew();
      void queryClient.invalidateQueries({ queryKey: ['stats-sources', 'list'] });
      void navigate(`/stats-sources/${result.sourceId}`, { replace: true });
    },
  });

  const setField = (name: keyof typeof head) => (value: string) => setHead((current) => ({ ...current, [name]: value }));
  const setRow = (index: number, name: keyof RowDraft, value: string) => setRows((current) => current.map((row, at) => (at === index ? { ...row, [name]: value } : row)));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    for (const [name, value] of Object.entries(head)) if (!value.trim()) errors[name] = '필수 항목입니다.';
    rows.forEach((row, index) => {
      const at = `rows[${index}]`;
      if (!row.ageGroupId.trim() || !row.ageGroupName.trim() || !row.genderId.trim() || !row.genderName.trim()) errors[at] = '구간·성별 분류의 식별자와 이름은 필수입니다.';
      else if (!isCount(row.count)) errors[at] = '인원은 0 이상의 정수입니다.';
      else if (!isAge(row.lowerAge) || !isAge(row.upperAge)) errors[at] = '연령은 0~999의 정수이거나 비워 둡니다.';
    });
    setMissing(errors);
    if (Object.keys(errors).length === 0) mutation.mutate();
  };
  const server = fieldErrors(mutation.error);
  const err = (name: string) => missing[name] ?? server[name];
  const rowErrors = rows.map((_, index) => err(`rows[${index}]`)).filter(Boolean);

  const text = (name: keyof typeof head, label: string, hint?: string, type: 'text' | 'date' = 'text') => (
    <Field id={`src-${name}`} label={label} required error={err(name)} hint={hint}>
      <input {...describe(`src-${name}`, err(name), hint)} type={type} value={head[name]} onChange={(event) => setField(name)(event.target.value)} />
    </Field>
  );

  return (
    <>
      <div className="adm-page-heading">
        <h1>집계자료 등록</h1>
      </div>
      <p className="adm-notice">기관이 제공한 집계만 입력합니다. 개인별 자료는 받지 않습니다. 등록하면 검토 대기가 되고 승인 담당자가 승인해야 통계에 쓰입니다. 같은 계열로 다시 등록하면 다음 버전이 됩니다.</p>
      <form className="adm-form" aria-label="집계자료" noValidate onSubmit={submit}>
        <div className="adm-form-grid">
          {text('provider', '출처 기관')}
          {text('basisId', '근거 식별자', '문서번호 등 출처를 찾을 수 있는 값입니다.')}
          {text('datasetId', '계열 키', '같은 자료의 새 버전은 같은 계열 키로 등록합니다.')}
          {text('periodStart', '집계 기간 시작', undefined, 'date')}
          {text('periodEnd', '집계 기간 끝', undefined, 'date')}
          {text('ageBasisDate', '연령 기준일', undefined, 'date')}
          <Field id="src-dedupeNote" label="모집단·중복 처리 기준" required full error={err('dedupeNote')}>
            <textarea {...describe('src-dedupeNote', err('dedupeNote'))} rows={3} value={head.dedupeNote} onChange={(event) => setField('dedupeNote')(event.target.value)} />
          </Field>
        </div>

        <h2 className="adm-section">집계 표</h2>
        <p className="adm-notice">구간과 성별 분류는 원자료의 이름을 그대로 적습니다. 합계·미상 분류도 그대로 입력하고, 실제 0명은 0으로 적습니다. 같은 구간·성별 조합은 한 번만 넣습니다.</p>
        <TableWrap label="집계 표 입력">
          <table>
            <thead>
              <tr>
                <th scope="col">연령구간 식별자</th>
                <th scope="col">연령구간 이름</th>
                <th scope="col">하한</th>
                <th scope="col">상한</th>
                <th scope="col">성별 식별자</th>
                <th scope="col">성별 이름</th>
                <th scope="col">인원</th>
                <th scope="col">행 관리</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const n = index + 1;
                const input = (name: keyof RowDraft, label: string, inputMode?: 'numeric') => (
                  <input aria-label={`${n}행 ${label}`} inputMode={inputMode} value={row[name]} onChange={(event) => setRow(index, name, event.target.value)} />
                );
                return (
                  <tr key={index}>
                    <td>{input('ageGroupId', '연령구간 식별자')}</td>
                    <td>{input('ageGroupName', '연령구간 이름')}</td>
                    <td>{input('lowerAge', '하한', 'numeric')}</td>
                    <td>{input('upperAge', '상한', 'numeric')}</td>
                    <td>{input('genderId', '성별 식별자')}</td>
                    <td>{input('genderName', '성별 이름')}</td>
                    <td>{input('count', '인원', 'numeric')}</td>
                    <td>
                      <button type="button" className="adm-button secondary" disabled={rows.length === 1} onClick={() => setRows((current) => current.filter((_, at) => at !== index))}>
                        {n}행 삭제
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </TableWrap>
        {rowErrors.map((message) => (
          <p key={message} className="adm-field-error" role="alert">
            {message}
          </p>
        ))}
        <div className="adm-actions">
          <button type="button" className="adm-button secondary" onClick={() => setRows((current) => [...current, emptyRow()])}>
            행 추가
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
          <Link className="adm-button secondary" to="/stats-sources">
            취소
          </Link>
        </div>
      </form>
    </>
  );
}
