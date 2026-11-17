// 환불 접수 요청. 금액은 보내지 않는다. 서버가 반환 기준액을 산정한다. 계좌는 수동 계좌환불을 고른 때만 세 값을 함께 보낸다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type Refund = Schemas['Refund'];

export type RefundAccount = { bankCode: string; accountHolder: string; accountNumber: string };

export const createRefund = (
  applicationId: string,
  reason: string | null,
  idempotencyKey: string,
  account?: RefundAccount,
) =>
  postJson<Refund>(
    '/me/refunds',
    { applicationId, reason, ...account },
    { headers: { 'Idempotency-Key': idempotencyKey } },
  );