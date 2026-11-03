// 수강신청 화면. 서버가 산정한 금액과 신청 가능 여부를 보여 주고, 신청 요청을 한 번만 보낸다
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { createApplication } from '../../api/applications';
import { applicationQuery, applyPreviewQuery } from '../../api/queries';
import { FormMessage } from '../../components/FormMessage';
import { QueryFallback } from '../../components/QueryFallback';
import { ServicePage } from '../../layout/SubLayout';
import { categoryText, formatFee, instructorText } from '../../lib/course';
import { errorMessage } from '../../lib/errors';
import { formatDate } from '../../lib/format';
import { formatSchedule } from '../../lib/schedule';
import { usePageTitle } from '../../lib/usePageTitle';

const TITLE = '수강신청';

export function ApplyPage() {
  const { courseId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery(applyPreviewQuery(courseId));
  usePageTitle(TITLE);
  // 화면을 연 동안의 신청 시도는 같은 멱등키를 쓴다. 다시 눌러도 서버가 중복 접수하지 않는다.
  const idempotencyKey = useRef(crypto.randomUUID());
  const sending = useRef(false);

  const submit = useMutation({
    mutationFn: () => createApplication(courseId, idempotencyKey.current),
    onSuccess: async (application) => {
      queryClient.setQueryData(applicationQuery(application.applicationId).queryKey, application);
      // 신청으로 강좌의 잔여석이 달라졌다. 신청 미리보기는 열 때마다 다시 받으므로 따로 지우지 않는다.
      await queryClient.invalidateQueries({ queryKey: ['courses'] });
      navigate(`/applications/${application.applicationId}/done`, { replace: true });
    },
    onSettled: () => {
      sending.current = false;
    },
  });

  const preview = query.data;
  if (!preview) return <QueryFallback query={query} what="신청 정보" />;

  const { course, eligibility } = preview;
  const schedule = formatSchedule(course.schedules);
  const waitingOnly = course.remainingSeats === 0;
  const minutes = Math.floor(preview.paymentWindowSeconds / 60);

  function send() {
    if (sending.current) return;
    sending.current = true;
    submit.mutate();
  }

  return (
    <ServicePage
      title={TITLE}
      crumbs={[
        { label: '강좌정보', to: '/courses' },
        { label: course.name, to: `/courses/${course.courseId}` },
        { label: TITLE },
      ]}
    >
      <div className="proto">
        <h2>신청 강좌</h2>
        <dl className="proto-info">
          <div>
            <dt>강좌명</dt>
            <dd>
              {course.name}
              <small> · {categoryText(course.category)}</small>
            </dd>
          </div>
          <div>
            <dt>강사</dt>
            <dd>{instructorText(course.instructorName)}</dd>
          </div>
          <div>
            <dt>교육기간</dt>
            <dd>
              {formatDate(course.educationStart)} – {formatDate(course.educationEnd)}
            </dd>
          </div>
          <div>
            <dt>요일·시간</dt>
            <dd>{[schedule.days, schedule.times].filter(Boolean).join(' ')}</dd>
          </div>
          <div>
            <dt>수강료</dt>
            <dd>{formatFee(preview.fee)}</dd>
          </div>
          <div>
            <dt>감면</dt>
            <dd>{formatFee(preview.reductionAmount)}</dd>
          </div>
          <div>
            <dt>결제금액</dt>
            <dd>
              <strong>{formatFee(preview.payableAmount)}</strong>
            </dd>
          </div>
        </dl>

        {eligibility.canApply ? (
          <>
            {waitingOnly ? (
              <p className="proto-hint">
                정원이 모두 찼습니다. 대기신청을 하면 순번이 정해지고 자리가 나면 결제할 수 있습니다.
              </p>
            ) : null}
            {preview.payableAmount > 0 ? (
              <p className="proto-hint">
                자리를 배정받으면 {minutes}분({preview.paymentWindowSeconds}초) 안에 결제해야 합니다. 새로고침·재접속·결제수단
                변경으로 기한이 늘어나지 않습니다.
              </p>
            ) : null}
            <div className="proto-form-actions">
              <button className="button" type="button" disabled={submit.isPending} onClick={send}>
                {waitingOnly ? '대기신청' : '수강신청'}
              </button>
            </div>
            <FormMessage text={submit.isError ? errorMessage(submit.error) : ''} error />
          </>
        ) : (
          <div className="empty-state" role="status">
            <h3>{eligibility.reasonMessage ?? '지금은 신청할 수 없습니다.'}</h3>
          </div>
        )}

        <div className="proto-actions">
          <Link className="button secondary" to={`/courses/${course.courseId}`}>
            강좌 상세
          </Link>
          {preview.alreadyApplied ? (
            <Link className="button secondary" to="/me/applications">
              신청내역
            </Link>
          ) : null}
        </div>
      </div>
    </ServicePage>
  );
}
