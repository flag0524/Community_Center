// 회원 조회 상세 화면. 가려진 연락처는 사유를 남겨야 열리고, 이용제한·탈퇴·이름 변경 검토는 사유만 기록한다. 회원 정보는 고칠 수 없다 (ADM-MBR-001P)
import type { Schemas } from '@jori/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { closeMemberReview, createMemberReview, recordResidence, revealMemberContact, type AdminMember, type MemberReview } from '../../api/members';
import { memberQuery } from '../../api/queries';
import { Field, describe } from '../../components/Field';
import { TableWrap } from '../../components/ListParts';
import { errorMessage, fieldErrors } from '../../lib/errors';
import { kstDateTime, won } from '../../lib/format';
import { DISPLAY_STATE, MEMBER_STATUS, PAYMENT_STATUS, RESIDENCE_DECLARED, RESIDENCE_STATUS, REVIEW_KIND, REVIEW_STATE } from '../../lib/labels';
import { useIdempotencyKey } from '../../lib/useIdempotencyKey';

export function MemberDetailPage() {
  const { memberId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(memberQuery(memberId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;
  return <MemberDetail key={data.memberId} member={data} />;
}

function MemberDetail({ member }: { member: AdminMember }) {
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: memberQuery(member.memberId).queryKey });
    queryClient.removeQueries({ queryKey: ['members', 'list'] });
  };

  return (
    <>
      <div className="adm-page-heading">
        <h1>회원 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>회원 ID</dt>
        <dd>{member.loginId}</dd>
        <dt>이름</dt>
        <dd>{member.nameMasked}</dd>
        <dt>연락처</dt>
        <ContactRows member={member} />
        <dt>가입일</dt>
        <dd>{member.joinedOn}</dd>
        <dt>이용상태</dt>
        <dd>{MEMBER_STATUS[member.status]}</dd>
        <dt>거주지</dt>
        <dd>
          입력 {member.residenceDeclared ? RESIDENCE_DECLARED[member.residenceDeclared] : '-'} · 확인 {RESIDENCE_STATUS[member.residenceStatus]}
        </dd>
      </dl>
      <p className="adm-notice">이 화면에서는 회원 정보를 고칠 수 없습니다. 이용제한·탈퇴·이름 변경은 검토 사유만 기록합니다.</p>

      <h2 className="adm-section">신청·결제 요약</h2>
      <p>
        신청 {member.applicationCount}건 · 결제완료 {won(member.paidTotal)}
      </p>
      {member.applications.length > 0 ? (
        <TableWrap label="신청 요약">
          <table>
            <thead>
              <tr>
                <th scope="col">신청번호</th>
                <th scope="col">강좌</th>
                <th scope="col">신청상태</th>
                <th scope="col">결제상태</th>
              </tr>
            </thead>
            <tbody>
              {member.applications.map((application) => (
                <tr key={application.applicationNo}>
                  <td>{application.applicationNo}</td>
                  <td>{application.courseName}</td>
                  <td>{DISPLAY_STATE[application.displayState]}</td>
                  <td>{application.paymentStatus ? PAYMENT_STATUS[application.paymentStatus] : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>신청 내역이 없습니다.</p>
      )}

      <h2 className="adm-section">검토 기록</h2>
      <ReviewSection member={member} onChanged={refresh} />

      {member.canReview && member.status !== 'WITHDRAWN' && <ResidenceForm member={member} onDone={refresh} />}

      <div className="adm-actions">
        <Link className="adm-button secondary" to="/mbr/members">
          목록
        </Link>
      </div>
    </>
  );
}

function ContactRows({ member }: { member: AdminMember }) {
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState('');
  const mutation = useMutation({ mutationFn: () => revealMemberContact(member.memberId, reason.trim()) });
  const server = fieldErrors(mutation.error);

  if (mutation.data) {
    return (
      <dd>
        {mutation.data.phone} · {mutation.data.email}
        <span className="adm-sub">조회 사유가 감사기록에 남았습니다. 화면을 닫으면 다시 가려집니다.</span>
      </dd>
    );
  }
  return (
    <dd>
      {member.phoneMasked} · {member.emailMasked}
      {member.canReview && !asking && (
        <>
          {' '}
          <button className="adm-button secondary" type="button" onClick={() => setAsking(true)}>
            원문 보기
          </button>
        </>
      )}
      {asking && (
        <div className="adm-notice">
          <Field id="reveal-reason" label="조회 사유" required error={server.reason} hint="사유는 감사기록에 남습니다.">
            <input {...describe('reveal-reason', server.reason, '사유는 감사기록에 남습니다.')} value={reason} maxLength={300} onChange={(event) => setReason(event.target.value)} />
          </Field>
          {mutation.isError && Object.keys(server).length === 0 && (
            <p className="adm-message error" role="alert">
              {errorMessage(mutation.error)}
            </p>
          )}
          <div className="adm-actions">
            <button className="adm-button" type="button" disabled={mutation.isPending || reason.trim().length < 5} onClick={() => mutation.mutate()}>
              원문 열기
            </button>
            <button className="adm-button secondary" type="button" onClick={() => setAsking(false)}>
              취소
            </button>
          </div>
        </div>
      )}
    </dd>
  );
}

function ReviewSection({ member, onChanged }: { member: AdminMember; onChanged: () => void }) {
  const key = useIdempotencyKey();
  const [kind, setKind] = useState<Schemas['MemberReviewKind']>('RESTRICT');
  const [reason, setReason] = useState('');
  const [missing, setMissing] = useState('');
  const create = useMutation({
    mutationFn: () => createMemberReview(member.memberId, { kind, reason: reason.trim() }, key.current()),
    onSuccess: () => {
      key.renew();
      setReason('');
      onChanged();
    },
  });
  const server = fieldErrors(create.error);

  return (
    <>
      {member.reviews.length > 0 ? (
        <TableWrap label="검토 기록">
          <table>
            <thead>
              <tr>
                <th scope="col">구분</th>
                <th scope="col">상태</th>
                <th scope="col">사유</th>
                <th scope="col">기록</th>
                <th scope="col">관리</th>
              </tr>
            </thead>
            <tbody>
              {member.reviews.map((review) => (
                <ReviewRow key={review.reviewId} memberId={member.memberId} review={review} canReview={member.canReview} onChanged={onChanged} />
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : (
        <p>검토 기록이 없습니다.</p>
      )}
      {member.canReview && member.status !== 'WITHDRAWN' && (
        <form
          className="adm-form"
          aria-label="검토 기록 추가"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (!reason.trim()) return setMissing('필수 항목입니다.');
            setMissing('');
            create.mutate();
          }}
        >
          <div className="adm-form-grid">
            <Field id="review-kind" label="검토 구분" required error={server.kind}>
              <select {...describe('review-kind', server.kind)} value={kind} onChange={(event) => setKind(event.target.value as Schemas['MemberReviewKind'])}>
                {Object.entries(REVIEW_KIND).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field id="review-reason" label="검토 사유" required error={missing || server.reason} hint="개인정보를 입력하지 마세요." full>
              <textarea {...describe('review-reason', missing || server.reason, '개인정보를 입력하지 마세요.')} rows={3} maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} />
            </Field>
          </div>
          {create.isError && Object.keys(server).length === 0 && (
            <p className="adm-message error" role="alert">
              {errorMessage(create.error)}
            </p>
          )}
          <div className="adm-actions">
            <button className="adm-button" type="submit" disabled={create.isPending}>
              검토 기록
            </button>
          </div>
        </form>
      )}
    </>
  );
}

function ReviewRow({ memberId, review, canReview, onChanged }: { memberId: string; review: MemberReview; canReview: boolean; onChanged: () => void }) {
  const [closing, setClosing] = useState(false);
  const [note, setNote] = useState('');
  const close = useMutation({
    mutationFn: () => closeMemberReview(memberId, review.reviewId, note.trim()),
    onSuccess: () => {
      setClosing(false);
      onChanged();
    },
  });
  return (
    <tr>
      <td>{REVIEW_KIND[review.kind]}</td>
      <td>{REVIEW_STATE[review.state]}</td>
      <td>
        {review.reason}
        {review.closedNote && <span className="adm-sub">처리: {review.closedNote}</span>}
      </td>
      <td>
        {review.recordedBy} · {kstDateTime(review.recordedAt)}
      </td>
      <td>
        {canReview && review.state === 'OPEN' && !closing && (
          <button className="adm-button secondary" type="button" aria-label={`처리 완료 (${REVIEW_KIND[review.kind]})`} onClick={() => setClosing(true)}>
            처리 완료
          </button>
        )}
        {closing && (
          <div>
            <label>
              처리 내용
              <input value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} />
            </label>
            <div className="adm-actions">
              <button className="adm-button" type="button" disabled={close.isPending || !note.trim()} onClick={() => close.mutate()}>
                완료 처리
              </button>
              <button className="adm-button secondary" type="button" onClick={() => setClosing(false)}>
                취소
              </button>
            </div>
            {close.isError && (
              <p className="adm-message error" role="alert">
                {errorMessage(close.error)}
              </p>
            )}
          </div>
        )}
      </td>
    </tr>
  );
}

function ResidenceForm({ member, onDone }: { member: AdminMember; onDone: () => void }) {
  const [result, setResult] = useState<Schemas['ResidenceStatus']>(member.residenceStatus);
  const [note, setNote] = useState('');
  const [missing, setMissing] = useState('');
  const mutation = useMutation({
    mutationFn: () => recordResidence(member.memberId, result, note.trim()),
    onSuccess: () => {
      setNote('');
      onDone();
    },
  });
  return (
    <>
      <h2 className="adm-section">거주지 확인 기록</h2>
      <form
        className="adm-form"
        aria-label="거주지 확인"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          if (!note.trim()) return setMissing('필수 항목입니다.');
          setMissing('');
          mutation.mutate();
        }}
      >
        <div className="adm-form-grid">
          <Field id="residence-result" label="확인 결과" required>
            <select {...describe('residence-result')} value={result} onChange={(event) => setResult(event.target.value as Schemas['ResidenceStatus'])}>
              {Object.entries(RESIDENCE_STATUS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field id="residence-note" label="확인 근거" required error={missing} hint="어떤 방법으로 확인했는지 적어 주세요." full>
            <input {...describe('residence-note', missing, '어떤 방법으로 확인했는지 적어 주세요.')} value={note} maxLength={300} onChange={(event) => setNote(event.target.value)} />
          </Field>
        </div>
        {mutation.isSuccess && (
          <p className="adm-message" role="status">
            기록했습니다.
          </p>
        )}
        {mutation.isError && (
          <p className="adm-message error" role="alert">
            {errorMessage(mutation.error)}
          </p>
        )}
        <div className="adm-actions">
          <button className="adm-button" type="submit" disabled={mutation.isPending}>
            확인 결과 기록
          </button>
        </div>
      </form>
    </>
  );
}
