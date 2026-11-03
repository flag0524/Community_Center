// 환불 접수 요청. 금액은 보내지 않는다. 서버가 반환 기준액을 산정한다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type Refund = Schemas['Refund'];

export const createRefund = (applicationId: string, reason: string | null, idempotencyKey: string) =>
  postJson<Refund>('/me/refunds', { applicationId, reason }, { headers: { 'Idempotency-Key': idempotencyKey } });