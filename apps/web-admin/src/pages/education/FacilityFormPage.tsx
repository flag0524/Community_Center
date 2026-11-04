// 센터·강의실 등록·수정 화면. 강의실은 상위 센터를 고르고 센터는 주소를 입력한다 (ADM-EDU-005P)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { createFacility, updateFacility, type FacilityWrite } from '../../api/campus';
import { facilityListQuery, facilityQuery, type Facility } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { FACILITY_KIND } from '../../lib/labels';
import { isVersionConflict } from '../../lib/messages';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

interface Values {
  kind: FacilityWrite['kind'];
  parentId: string;
  name: string;
  floor: string;
  address: string;
  isPublic: boolean;
  inUse: boolean;
}

const BLANK: Values = { kind: 'ROOM', parentId: '', name: '', floor: '', address: '', isPublic: true, inUse: true };

const fromFacility = (facility: Facility): Values => ({
  kind: facility.kind,
  parentId: facility.parentId ?? '',
  name: facility.name,
  floor: facility.floor ?? '',
  address: facility.address ?? '',
  isPublic: facility.isPublic,
  inUse: facility.inUse,
});

export function FacilityFormPage({ mode }: { mode: 'create' | 'edit' }) {
  const { facilityId = '' } = useParams();
  const list = useQuery(facilityListQuery);
  const detail = useQuery({ ...facilityQuery(facilityId), enabled: mode === 'edit' });
  const failed = list.isError ? list.error : detail.isError ? detail.error : null;
  if (failed) return <p role="alert">{errorMessage(failed)}</p>;
  if (!list.data || (mode === 'edit' && !detail.data)) return <p role="status">불러오는 중입니다.</p>;
  const centers = list.data.items.filter((item) => item.kind === 'CENTER');
  const facility = detail.data;
  return mode === 'edit' && facility ? (
    <FacilityForm key={facility.facilityId} centers={centers} facility={facility} />
  ) : (
    <FacilityForm key="new" centers={centers} />
  );
}

function FacilityForm({ centers, facility }: { centers: Facility[]; facility?: Facility }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = useIdempotencyKey();
  const [values, setValues] = useState<Values>(facility ? fromFacility(facility) : { ...BLANK, parentId: centers[0]?.facilityId ?? '' });
  const [missing, setMissing] = useState<Partial<Record<keyof Values, string>>>({});
  const [saved, setSaved] = useState(false);
  const isRoom = values.kind === 'ROOM';

  const mutation = useMutation({
    mutationFn: (body: FacilityWrite) =>
      facility ? updateFacility(facility.facilityId, body, facility.version) : createFacility(body, key.current()),
    onSuccess: (result) => {
      key.renew();
      // 시설이 바뀌면 일정 양식의 강의실 선택지도 달라진다.
      queryClient.removeQueries({ queryKey: ['facilities', 'list'] });
      queryClient.removeQueries({ queryKey: ['course-options'] });
      if (facility) {
        queryClient.setQueryData(facilityQuery(result.facilityId).queryKey, result);
        setSaved(true);
      } else void navigate(`/edu/facilities/${result.facilityId}`, { replace: true });
    },
  });

  const change = <K extends keyof Values>(name: K, value: Values[K]) => {
    setSaved(false);
    setValues((current) => ({ ...current, [name]: value }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Partial<Record<keyof Values, string>> = {};
    if (!values.name.trim()) errors.name = '필수 항목입니다.';
    if (isRoom && !values.parentId) errors.parentId = '필수 항목입니다.';
    setMissing(errors);
    if (Object.keys(errors).length > 0) return;
    mutation.mutate({
      kind: values.kind,
      parentId: isRoom ? values.parentId : null,
      name: values.name.trim(),
      floor: values.floor.trim() || null,
      address: !isRoom && values.address.trim() ? values.address.trim() : null,
      isPublic: values.isPublic,
      inUse: values.inUse,
    });
  };

  const server = fieldErrors(mutation.error);
  const err = (name: keyof Values) => missing[name] ?? server[name];

  return (
    <>
      <div className="adm-page-heading">
        <h1>{facility ? '센터·강의실 수정' : '센터·강의실 등록'}</h1>
      </div>
      <form className="adm-form" aria-label="센터·강의실" noValidate onSubmit={submit}>
        <div className="adm-form-grid">
          <Field id="facility-kind" label="구분" required>
            <select {...describe('facility-kind')} value={values.kind} disabled={facility !== undefined} onChange={(event) => change('kind', event.target.value as Values['kind'])}>
              {Object.entries(FACILITY_KIND).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          {isRoom && (
            <Field id="facility-parent" label="상위 시설" required error={err('parentId')}>
              <select {...describe('facility-parent', err('parentId'))} value={values.parentId} onChange={(event) => change('parentId', event.target.value)}>
                <option value="">선택</option>
                {centers.map((center) => (
                  <option key={center.facilityId} value={center.facilityId}>
                    {center.name}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field id="facility-name" label="시설명" required error={err('name')}>
            <input {...describe('facility-name', err('name'))} value={values.name} maxLength={100} onChange={(event) => change('name', event.target.value)} />
          </Field>
          <Field id="facility-floor" label="층">
            <input {...describe('facility-floor')} value={values.floor} maxLength={20} onChange={(event) => change('floor', event.target.value)} />
          </Field>
          {!isRoom && (
            <Field id="facility-address" label="주소" full>
              <input {...describe('facility-address')} value={values.address} maxLength={200} onChange={(event) => change('address', event.target.value)} />
            </Field>
          )}
          <Field id="facility-public" label="공개 여부">
            <select {...describe('facility-public')} value={values.isPublic ? 'Y' : 'N'} onChange={(event) => change('isPublic', event.target.value === 'Y')}>
              <option value="Y">공개</option>
              <option value="N">비공개</option>
            </select>
          </Field>
          <Field id="facility-in-use" label="사용 여부" hint={values.inUse ? undefined : '사용을 중지하면 기존 일정은 유지되고 새 일정에는 배정할 수 없습니다.'}>
            <select {...describe('facility-in-use', undefined, values.inUse ? undefined : '사용을 중지하면 기존 일정은 유지되고 새 일정에는 배정할 수 없습니다.')} value={values.inUse ? 'Y' : 'N'} onChange={(event) => change('inUse', event.target.value === 'Y')}>
              <option value="Y">사용중</option>
              <option value="N">사용중지</option>
            </select>
          </Field>
        </div>
        {facility && facility.scheduleCount > 0 && <p className="adm-notice">이 시설을 쓰는 일정이 {facility.scheduleCount}건 있습니다.</p>}
        {saved && (
          <p className="adm-message" role="status">
            저장했습니다.
          </p>
        )}
        {mutation.isError && (
          <p className="adm-message error" role="alert">
            {isVersionConflict(mutation.error)
              ? '다른 곳에서 먼저 수정되었습니다. 목록으로 돌아가 최신 내용을 다시 열어 주세요.'
              : errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          <button className="adm-button" type="submit" disabled={mutation.isPending}>
            저장
          </button>
          <Link className="adm-button secondary" to="/edu/facilities">
            목록
          </Link>
        </div>
      </form>
    </>
  );
}
