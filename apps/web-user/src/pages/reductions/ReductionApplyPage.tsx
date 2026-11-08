// 감면 사전심사 신청. 기수와 감면 유형만 고르고 금액·비율은 보내지 않는다. 증빙은 신청한 뒤 상세에서 올린다
import type { Schemas } from '@jori/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { createReduction } from '../../api/reductions';
import { reductionOptionsQuery } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';
import { REDUCTION_TYPE_LABEL } from './labels';

const TITLE = '감면 신청';
const TYPES = Object.keys(REDUCTION_TYPE_LABEL) as Array<Schemas['ReductionType']>;

function ApplyForm({ cycles }: { cycles: Array<{ id: string; name: string }> }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [cycleId, setCycleId] = useState(cycles[0]?.id ?? '');
  const [type, setType] = useState<Schemas['ReductionType'] | ''>('');
  const [missing, setMissing] = useState('');
  const idempotencyKey = useRef(crypto.randomUUID());
  const sending = useRef(false);

  const save = useMutation({
    mutationFn: () => createReduction({ cycleId, reductionType: type as Schemas['ReductionType'] }, idempotencyKey.current),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ['me', 'reductions'] });
      navigate(`/me/reductions/${created.reviewId}`, { replace: true, state: { created: true } });
    },
    onSettled: () => {
      sending.current = false;
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setMissing(type ? '' : '감면 유형을 선택해 주세요.');
    if (!type || sending.current) return;
    sending.current = true;
    save.mutate();
  }

  const server = fieldErrors(save.error);
  return (
    <form className="proto-form" aria-label="감면 신청" noValidate onSubmit={submit}>
      <label className="field">
        교육기수
        <select value={cycleId} onChange={(event) => setCycleId(event.target.value)}>
          {cycles.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {server.cycleId ? <p className="field-error">{server.cycleId}</p> : null}
      <fieldset>
        <legend>감면 유형</legend>
        {TYPES.map((value) => (
          <label key={value} className="proto-check">
            <input type="radio" name="reductionType" checked={type === value} onChange={() => setType(value)} /> {REDUCTION_TYPE_LABEL[value]}
          </label>
        ))}
        {missing || server.reductionType ? <p className="field-error">{missing || server.reductionType}</p> : null}
      </fieldset>
      <p className="proto-hint">신청한 뒤 상세 화면에서 증빙 파일을 올려 주세요. 증빙이 있어야 심사할 수 있습니다.</p>
      <div className="proto-form-actions">
        <button className="button" type="submit" disabled={save.isPending}>
          신청
        </button>
      </div>
      <FormMessage text={save.isError && Object.keys(server).length === 0 ? errorMessage(save.error) : ''} error />
    </form>
  );
}

export function ReductionApplyPage() {
  usePageTitle(TITLE);
  const options = useQuery(reductionOptionsQuery);
  const crumbs = [{ label: '마이페이지' }, { label: '감면 심사', to: '/me/reductions' }, { label: TITLE }];
  let body;
  if (!options.data) body = <QueryFallback query={options} what="신청 정보" />;
  else if (!options.data.canApply) body = <p className="proto-hint">{options.data.blockReason ?? '지금은 감면을 신청할 수 없습니다.'}</p>;
  else body = <ApplyForm cycles={options.data.cycles} />;
  return (
    <ServicePage title={TITLE} crumbs={crumbs}>
      <div className="proto">{body}</div>
    </ServicePage>
  );
}