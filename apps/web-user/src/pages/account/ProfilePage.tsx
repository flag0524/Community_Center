// 회원정보수정. 아이디·이름·휴대전화는 읽기 전용이고 이메일과 본인 입력 거주지역만 고친다. 거주지 확인은 센터가 한다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { updateProfile } from '../../api/member';
import { profileQuery, type MemberProfile } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { QueryFallback } from '../../components/QueryFallback';
import { TextField } from '../../components/TextField';
import { ServicePage } from '../../layout/SubLayout';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '회원정보수정';
const EMAIL_FORMAT = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function ProfileForm({ profile }: { profile: MemberProfile }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState(profile.email ?? '');
  const [residence, setResidence] = useState<string>(profile.residenceDeclared ?? '');
  const [emailError, setEmailError] = useState<string>();
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: () =>
      updateProfile({
        email: email.trim(),
        residenceDeclared: residence === '' ? null : (residence as 'JORI' | 'OTHER_PAJU'),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(profileQuery.queryKey, data);
      setSaved(true);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    if (!EMAIL_FORMAT.test(email.trim())) {
      setEmailError('이메일 주소 형식을 확인해 주세요.');
      return;
    }
    setEmailError(undefined);
    save.mutate();
  }

  const serverEmail = fieldErrors(save.error).email;
  const message = saved ? '저장되었습니다.' : save.isError ? errorMessage(save.error) : '';

  return (
    <form className="proto-form" aria-label="회원정보" noValidate onSubmit={submit}>
      <dl className="proto-info">
        <div>
          <dt>아이디</dt>
          <dd>{profile.loginId}</dd>
        </div>
        <div>
          <dt>이름</dt>
          <dd>{profile.name}</dd>
        </div>
        <div>
          <dt>휴대전화</dt>
          <dd>{profile.phoneMasked ?? '-'}</dd>
        </div>
        <div>
          <dt>거주지 확인</dt>
          <dd>{profile.residenceStatus === 'VERIFIED' ? '센터 확인 완료' : '센터 확인 전'}</dd>
        </div>
      </dl>
      <TextField
        label="이메일"
        name="email"
        type="email"
        autoComplete="email"
        maxLength={254}
        value={email}
        error={emailError ?? serverEmail}
        onChange={(event) => setEmail(event.target.value)}
      />
      <label className="field">
        거주지역 (본인 입력)
        <select value={residence} onChange={(event) => setResidence(event.target.value)}>
          <option value="">선택하지 않음</option>
          <option value="JORI">조리읍</option>
          <option value="OTHER_PAJU">그 외 파주시</option>
        </select>
      </label>
      <p className="proto-hint">우선접수는 센터가 확인한 거주지로 판정합니다. 이 항목은 참고용이며 센터 확인을 대신하지 않습니다.</p>
      <div className="proto-form-actions">
        <button className="button" type="submit" disabled={save.isPending}>
          저장
        </button>
      </div>
      <FormMessage text={message} error={!saved && save.isError} />
    </form>
  );
}

export function ProfilePage() {
  usePageTitle(TITLE);
  const query = useQuery(profileQuery);
  const profile = query.data;
  if (!profile) return <QueryFallback query={query} what="회원정보" />;

  return (
    <ServicePage title={TITLE} crumbs={[{ label: '마이페이지' }, { label: TITLE }]}>
      <div className="proto">
        <ProfileForm profile={profile} />
        <div className="proto-actions">
          <Link className="button secondary" to="/me/password">
            비밀번호 변경
          </Link>
          <Link className="button secondary" to="/me/withdraw">
            회원탈퇴
          </Link>
        </div>
      </div>
    </ServicePage>
  );
}