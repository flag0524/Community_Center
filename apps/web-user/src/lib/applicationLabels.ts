// 서버가 판정한 신청·결제·환불 상태를 화면 문구로 옮긴다. 상태 자체는 계산하지 않는다
import type { Schemas } from '@jori/api-client';

type Application = Schemas['ApplicationSummary'];

const STATE_LABEL: Record<Schemas['ApplicationDisplayState'], string> = {
  WAITING: '대기',
  PAYMENT_DUE: '결제대기',
  PAYMENT_FAILED: '결제실패',
  PAYMENT_UNKNOWN: '결제 결과 확인 중',
  CONFIRMED: '등록완료',
  CONFIRMED_FREE: '등록완료',
  EXPIRED: '결제기한 만료',
  CANCELLED: '신청취소',
  COURSE_CLOSED: '폐강',
  COMPLETED: '수강종료',
};

export const applicationStateText = (application: Application): string =>
  application.displayState === 'WAITING' && application.waitingRank
    ? `대기 ${application.waitingRank}번`
    : STATE_LABEL[application.displayState];

export function paymentStatusText(application: Application): string {
  if (application.displayState === 'CONFIRMED_FREE') return '결제 불필요';
  if (application.displayState === 'WAITING') return '결제 전';
  switch (application.paymentStatus) {
    case 'PAID':
      return '결제완료';
    case 'FAILED':
      return '결제실패';
    case 'PENDING':
      return '확인 중';
    case 'CANCELLED':
      return '결제취소';
    default:
      return '미결제';
  }
}

const REFUND_STAGE_LABEL: Record<Schemas['RefundStage'], string> = {
  RECEIVED: '접수',
  PROCESSING: '처리 중',
  ON_HOLD: '보류',
  DONE: '환불완료',
  REJECTED: '반려',
};

export const refundStageText = (stage: Schemas['RefundStage']): string => REFUND_STAGE_LABEL[stage];

export const PAYMENT_METHOD_LABEL: Record<Schemas['PaymentMethod'], string> = {
  CARD: '신용·체크카드',
  TRANSFER: '실시간 계좌이체',
};