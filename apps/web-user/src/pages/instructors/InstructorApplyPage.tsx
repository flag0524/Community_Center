// 강사 지원서 작성·수정. 텍스트 항목만 받고 증빙 파일은 첨부 설계 뒤에 더한다. 지원 가능 여부는 서버가 최종 판정한다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { createInstructorApplication, updateInstructorApplication } from '../../api/instructors';
import { categoriesQuery, instructorApplicationQuery, profileQuery, type InstructorApplication } from '../../api/queries';
import { MyFiles } from '../../components/MyFiles';
import { FormMessage } from '../../components/FormMessage';
import { QueryFallback } from '../../components/QueryFallback';
import { TextField } from '../../components/TextField';
import { ServicePage } from '../../layout/SubLayout';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '강사 지원서';

function ApplyForm({
  recruitmentId,
  categories,
  initial,
  applicationId,
  name,
  phone,
}: {
  recruitmentId: string;
  categories: Array<{ categoryId: string; name: string }>;
  initial?: InstructorApplication;
  applicationId?: string;
  name: string;
  phone: string;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [course, setCourse] = useState(initial?.desiredCourse ?? '');
  const [categoryId, setCategoryId] = useState(initial?.categoryId ?? categories[0]?.categoryId ?? '');
  const [career, setCareer] = useState(initial?.career ?? '');
  const [confirmed, setConfirmed] = useState(false);
  const [errors, setErrors] = useState<{ course?: string; career?: string; confirmed?: string }>({});
  const idempotencyKey = useRef(crypto.randomUUID());
  const sending = useRef(false);

  const save = useMutation({
    mutationFn: () => {
      const body = { recruitmentId, desiredCourse: course.trim(), categoryId, career: career.trim() };
      return applicationId ? updateInstructorApplication(applicationId, body) : createInstructorApplication(body, idempotencyKey.current);
    },
    onSuccess: () => {
      // 지원내역이 갱신 전의 옛 값을 잠깐 보이지 않도록 옛 목록·상세 캐시를 지운다.
      queryClient.removeQueries({ queryKey: ['me', 'instructor-applications'] });
      queryClient.removeQueries({ queryKey: ['me', 'instructor-application'] });
      queryClient.removeQueries({ queryKey: ['me', 'recruitment'] });
      navigate('/me/instructor-applications', { replace: true });
    },
    onSettled: () => {
      sending.current = false;
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const found = {
      course: course.trim() ? undefined : '희망 강좌명을 입력해 주세요.',
      career: career.trim() ? undefined : '경력 및 강의소개를 입력해 주세요.',
      confirmed: confirmed ? undefined : '제출 내용을 확인해 주세요.',
    };
    setErrors(found);
    if (found.course || found.career || found.confirmed || sending.current) return;
    sending.current = true;
    save.mutate();
  }

  const server = fieldErrors(save.error);
  return (
    <form className="proto-form" aria-label="강사 지원서" noValidate onSubmit={submit}>
      <dl className="proto-info">
        <div>
          <dt>이름</dt>
          <dd>{name}</dd>
        </div>
        <div>
          <dt>휴대전화</dt>
          <dd>{phone}</dd>
        </div>
      </dl>
      <TextField
        label="희망 강좌명"
        name="desiredCourse"
        type="text"
        maxLength={100}
        autoComplete="off"
        placeholder="희망 강좌명을 입력해 주세요."
        value={course}
        error={errors.course ?? server.desiredCourse}
        onChange={(event) => setCourse(event.target.value)}
      />
      <label className="field">
        희망 분야
        <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
          {categories.map((item) => (
            <option key={item.categoryId} value={item.categoryId}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        경력 및 강의소개
        <textarea
          rows={6}
          maxLength={2000}
          placeholder="강의 경력과 소개를 작성해 주세요."
          value={career}
          aria-invalid={errors.career ? true : undefined}
          aria-describedby={errors.career ? 'apply-career-error' : undefined}
          onChange={(event) => setCareer(event.target.value)}
        />
      </label>
      {errors.career ?? server.career ? (
        <p className="field-error" id="apply-career-error">
          {errors.career ?? server.career}
        </p>
      ) : null}
      <label className="proto-check">
        <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /> 제출 내용을 확인했습니다.
      </label>
      {errors.confirmed ? <p className="field-error">{errors.confirmed}</p> : null}
      <div className="proto-form-actions">
        <button className="button" type="submit" disabled={save.isPending}>
          {applicationId ? '저장' : '신청'}
        </button>
      </div>
      <FormMessage text={save.isError && Object.keys(server).length === 0 ? errorMessage(save.error) : ''} error />
    </form>
  );
}

export function InstructorApplyPage({ mode }: { mode: 'create' | 'edit' }) {
  const params = useParams();
  usePageTitle(TITLE);
  const categories = useQuery(categoriesQuery);
  const profile = useQuery(profileQuery);
  const existing = useQuery({ ...instructorApplicationQuery(params.applicationId ?? ''), enabled: mode === 'edit' });
  const crumbs = [{ label: '강사은행' }, { label: '강사등록신청', to: '/instructors/recruit' }, { label: TITLE }];

  let body;
  if (!categories.data) body = <QueryFallback query={categories} what="희망 분야" />;
  else if (!profile.data) body = <QueryFallback query={profile} what="회원정보" />;
  else if (mode === 'edit' && !existing.data) body = <QueryFallback query={existing} what="지원서" />;
  else {
    body = (
      <>
        <ApplyForm
          recruitmentId={mode === 'edit' ? existing.data!.recruitmentId : (params.recruitmentId ?? '')}
          categories={categories.data.items}
          initial={existing.data}
          applicationId={mode === 'edit' ? params.applicationId : undefined}
          name={profile.data.name}
          phone={profile.data.phoneMasked ?? '-'}
        />
        {mode === 'edit' ? (
          <MyFiles ownerPath={`/me/instructor-applications/${params.applicationId}`} label="증빙 파일" />
        ) : (
          <p className="proto-hint">증빙 파일은 지원서를 신청한 뒤 수정 화면에서 추가할 수 있습니다.</p>
        )}
      </>
    );
  }

  return (
    <ServicePage title={TITLE} crumbs={crumbs}>
      <div className="proto">{body}</div>
    </ServicePage>
  );
}