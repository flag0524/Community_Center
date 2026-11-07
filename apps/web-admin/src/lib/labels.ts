// 서버가 준 상태 코드를 화면 문구로 바꾸는 표. 상태 판정은 서버가 하고 화면은 이름만 붙인다
import type { Schemas } from '@jori/api-client';

export const COURSE_STATUS: Record<Schemas['CourseAdminStatus'], string> = {
  DRAFT: '작성중',
  PUBLISHED: '공개',
  RECEPTION_CLOSED: '접수마감',
  CANCELLED: '폐강',
};

export const RECEPTION_STATE: Record<Schemas['ReceptionState'], string> = {
  UPCOMING: '접수예정',
  OPEN: '접수중',
  CLOSED: '접수종료',
};

export const EDUCATION_STATE: Record<Schemas['EducationState'], string> = {
  UPCOMING: '교육예정',
  ONGOING: '교육중',
  ENDED: '교육종료',
};

export const CYCLE_STATUS: Record<Schemas['CycleStatus'], string> = {
  DRAFT: '작성중',
  ACTIVE: '사용중',
  INACTIVE: '사용중지',
};

export const WEEKDAY: Record<Schemas['Weekday'], string> = {
  MON: '월',
  TUE: '화',
  WED: '수',
  THU: '목',
  FRI: '금',
  SAT: '토',
  SUN: '일',
};

export const CHANGE_KIND: Record<Schemas['ScheduleChangeKind'], string> = { CANCEL: '휴강', MAKEUP: '보강' };

export const FACILITY_KIND: Record<Schemas['FacilityKind'], string> = { CENTER: '센터', ROOM: '강의실' };

export const REVIEW_STATUS: Record<Schemas['ReviewStatus'], string> = {
  PENDING: '심사대기',
  APPROVED: '승인',
  REJECTED: '반려',
  SUSPENDED: '활동중지',
};

export const APPLICATION_SOURCE: Record<Schemas['ApplicationSource'], string> = {
  ONLINE: '온라인 지원',
  VISIT: '방문 접수',
  EXTERNAL: '외부 접수',
};

export const INPUT_STATUS: Record<Schemas['AttendanceInputStatus'], string> = { IN_PROGRESS: '입력중', DONE: '완료' };

export const ATTENDANCE_MARK: Record<Schemas['AttendanceMark'], string> = { PRESENT: '출석', ABSENT: '결석', UNCHECKED: '미체크' };

export const DISPLAY_STATE: Record<Schemas['ApplicationDisplayState'], string> = {
  WAITING: '대기',
  PAYMENT_DUE: '결제대기',
  PAYMENT_FAILED: '결제실패',
  PAYMENT_UNKNOWN: '결제 결과 확인 중',
  CONFIRMED: '수강확정',
  CONFIRMED_FREE: '수강확정(무료)',
  EXPIRED: '결제기한 만료',
  CANCELLED: '신청취소',
  COURSE_CLOSED: '폐강',
  COMPLETED: '수강종료',
};

export const APPLICATION_STATUS: Record<Schemas['ApplicationStatus'], string> = {
  WAITING: '대기',
  HOLD: '자리 점유(결제 대기)',
  CONFIRMED: '확정',
  CANCELLED: '취소',
  EXPIRED: '만료',
  COMPLETED: '종료',
};

export const PAYMENT_STATUS: Record<Schemas['PaymentStatus'], string> = {
  READY: '결제 준비',
  PENDING: '승인 결과 확인 중',
  PAID: '결제완료',
  FAILED: '결제실패',
  CANCELLED: '결제취소',
};

export const REFUND_STATUS: Record<Schemas['RefundStatus'], string> = {
  REQUESTED: '접수',
  ON_HOLD: '보류',
  REJECTED: '반려',
  APPROVED: '승인',
  PENDING: '처리중',
  DONE: '완료',
  FAILED: '실패',
};

export const PAYMENT_METHOD: Record<Schemas['PaymentMethod'], string> = { CARD: '카드', TRANSFER: '계좌이체' };

export const SMS_RESULT: Record<Schemas['SmsResult'], string> = { PENDING: '발송 대기', SENT: '발송 완료', FAILED: '발송 실패' };

export const REPLAY_OUTCOME: Record<Schemas['ReplayOutcome'], string> = { SAME_RESULT: '이전 결과 반환', CONFLICT: '내용 불일치(409)' };

export const NOTICE_HANDLING: Record<Schemas['NoticeHandling'], string> = {
  DONE: '처리 완료',
  DUPLICATE: '중복(기존 결과 반환)',
  CONFLICT: '충돌(격리, 보안사건)',
};

export const ACTION_KIND: Record<Schemas['ActionKind'], string> = { RECHECK: 'PG 재조회', MANUAL_RECONCILE: '수동 대사' };

export const RECONCILE_OUTCOME: Record<Schemas['ReconcileOutcome'], string> = { PAID: '성공', FAILED: '실패' };

export const REFUND_REQUESTER: Record<Schemas['RefundRequester'], string> = { MEMBER: '회원 요청', ADMIN: '담당자 대리 접수' };

export const EXECUTION_METHOD: Record<Schemas['ExecutionMethod'], string> = { CANCEL_PAYMENT: '원결제 취소', MANUAL_TRANSFER: '수동 계좌환불' };

export const REFUND_RULE: Record<Schemas['RefundRule'], string> = { BEFORE_START: '개강 전 전액', AFTER_START: '개강 후 당월분 제외' };

export const MEMBER_STATUS: Record<Schemas['MemberStatus'], string> = { ACTIVE: '정상', LOCKED: '잠금', WITHDRAWN: '탈퇴' };

export const RESIDENCE_DECLARED: Record<Schemas['ResidenceDeclared'], string> = { JORI: '조리읍', OTHER_PAJU: '파주시 다른 지역' };

export const RESIDENCE_STATUS: Record<Schemas['ResidenceStatus'], string> = { UNVERIFIED: '확인 전', VERIFIED: '확인 완료' };

export const REVIEW_KIND: Record<Schemas['MemberReviewKind'], string> = { RESTRICT: '이용제한 검토', WITHDRAW: '탈퇴 검토', NAME_CHANGE: '이름 변경 요청 검토' };

export const REVIEW_STATE: Record<Schemas['MemberReviewState'], string> = { OPEN: '검토 중', CLOSED: '처리 완료' };

export const INQUIRY_STATUS: Record<Schemas['InquiryStatus'], string> = { RECEIVED: '접수', ANSWERED: '답변완료' };

export const ANSWER_ACTION: Record<Schemas['AnswerAction'], string> = { CREATED: '답변 작성', EDITED: '답변 수정' };

export const CONTENT_TYPE: Record<Schemas['ContentType'], string> = {
  VISUAL: '비주얼',
  BANNER: '배너',
  POPUP: '팝업',
  HISTORY: '연혁',
  INTRO: '센터소개',
  CONTACT: '연락처',
  GUIDE: '수강·환불 안내',
  FACILITY: '시설안내',
};

export const TERM_TYPE: Record<Schemas['TermType'], string> = {
  TERMS_OF_USE: '이용약관',
  PRIVACY_CONSENT: '개인정보 수집·이용 동의',
  MARKETING_CONSENT: '마케팅 수신 동의',
  PRIVACY_POLICY: '개인정보처리방침',
  EMAIL_REFUSAL: '이메일 무단수집 거부',
};
export const TERM_STATUS: Record<Schemas['TermStatus'], string> = { REVIEW: '검토', FIXED: '확정', PUBLISHED: '게시', ENDED: '게시 종료' };
export const FILE_STATUS: Record<Schemas['FileStatus'], string> = { PENDING: '검사 대기', SAFE: '정상', BLOCK: '차단', DELETE: '삭제' };
export const FILE_OWNER: Record<Schemas['FileOwnerKind'], string> = {
  POST: '게시물',
  COURSE: '강좌',
  INSTRUCTOR_APPLICATION: '강사 지원',
  CONTENT: '홈·센터 콘텐츠',
  APPLICATION: '수강신청',
  REFUND: '환불',
  STATS_SOURCE: '통계 자료',
};
export const FILE_PURPOSE: Record<Schemas['FilePurpose'], string> = { ATTACH: '첨부', PLAN: '강의계획서', PROOF: '증빙', IMAGE: '이미지' };

export const DASHBOARD_TASK: Record<Schemas['DashboardTaskKind'], string> = {
  PAYMENT_UNKNOWN: '승인 결과 확인',
  REFUND_REVIEW: '환불 검토 대기',
  INSTRUCTOR_REVIEW: '강사 심사 대기',
  INQUIRY_ANSWER: '문의 답변 대기',
  SMS_FAILED: '문자 발송 실패',
};
// 확인할 업무를 누르면 해당 목록에 조건을 걸어 연다
export const DASHBOARD_TASK_LINK: Record<Schemas['DashboardTaskKind'], string> = {
  PAYMENT_UNKNOWN: '/pay/transactions?status=PENDING',
  REFUND_REVIEW: '/pay/refunds?status=REQUESTED',
  INSTRUCTOR_REVIEW: '/edu/instructors?status=PENDING',
  INQUIRY_ANSWER: '/mbr/inquiries?status=RECEIVED',
  SMS_FAILED: '/sys/sms',
};

export const SMS_KIND: Record<Schemas['SmsKind'], string> = { AUTO: '자동 알림', MANUAL: '관리자 발송' };
export const SMS_SCOPE: Record<Schemas['SmsScope'], string> = { CENTER: '센터 전체', COURSE: '선택 강좌', EVENT: '업무사건' };
export const SMS_TARGET_STATE: Record<Schemas['SmsTargetState'], string> = { WAIT: '발송 대기', SENDING: '요청 중', SENT: '성공', FAIL: '실패', UNKNOWN: '확인 중', SKIP: '제외' };
export const SMS_AUDIENCE: Record<Schemas['SmsAudienceStatus'], string> = { CONFIRMED: '수강확정', PAYMENT_PENDING: '결제대기', WAITING: '대기' };

export const ASSIGNMENT_SCOPE: Record<Schemas['AssignmentScope'], string> = { SYSTEM: '전체 운영구조', GROUP: '운영묶음 전체', DONG: '동' };
export const ASSIGNMENT_STATUS: Record<Schemas['AssignmentStatus'], string> = { ACTIVE: '유효', SCHEDULED: '시작 전', EXPIRED: '기간 종료', REVOKED: '회수됨' };

export const REDUCTION_TYPE: Record<Schemas['ReductionType'], string> = { LIVELIHOOD: '기초생활보장 수급자 본인', VETERAN: '국가유공자 본인', DISABLED: '등록 장애인 본인' };
export const REDUCTION_STATUS: Record<Schemas['ReductionStatus'], string> = { RECEIVED: '접수', APPROVED: '승인', REJECTED: '반려', REVOKED: '철회' };
export const REDUCTION_DECISION: Record<Schemas['ReductionDecision'], string> = { APPROVE: '승인', REJECT: '반려' };

export const OPER_RULE_STATUS: Record<Schemas['OperRuleStatus'], string> = { REVIEW: '검토 중', DECIDED: '확정', HOLD: '보류' };