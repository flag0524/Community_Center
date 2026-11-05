// 환불 검토 요청. 접수는 멱등키를 싣고 결정·집행은 읽은 환불 건의 버전을 함께 보낸다
import type { Schemas } from '@jori/api-client';
import { postJson, putJson } from './http';

export type AdminRefund = Schemas['AdminRefund'];
export type AdminRefundCreate = Schemas['AdminRefundCreate'];

const id = encodeURIComponent;
const path = (refundId: string, action: string) => `/refunds/${id(refundId)}/${action}`;

export const createAdminRefund = (body: AdminRefundCreate, key: string) =>
  postJson<AdminRefund>('/refunds', body, { headers: { 'Idempotency-Key': key } });
export const holdRefund = (refundId: string, reason: string, version: number) =>
  putJson<AdminRefund>(path(refundId, 'hold'), { reason, version });
export const releaseRefundHold = (refundId: string, version: number) => postJson<AdminRefund>(path(refundId, 'release-hold'), { version });
export const approveRefund = (refundId: string, amount: number, version: number) =>
  putJson<AdminRefund>(path(refundId, 'approve'), { amount, version });
export const rejectRefund = (refundId: string, reason: string, version: number) =>
  putJson<AdminRefund>(path(refundId, 'reject'), { reason, version });
export const executeRefund = (refundId: string, version: number) => postJson<AdminRefund>(path(refundId, 'execute'), { version });
export const confirmRefundDone = (refundId: string, version: number) => postJson<AdminRefund>(path(refundId, 'confirm-done'), { version });