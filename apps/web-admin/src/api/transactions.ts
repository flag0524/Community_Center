// 결제·거래 대조 조치 요청. PG 재조회와 수동 대사는 읽은 거래 상태를 바탕으로 서버가 다시 판정한다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type Transaction = Schemas['Transaction'];
export type ReconcileRequest = Schemas['ReconcileRequest'];

const id = encodeURIComponent;

export const recheckTransaction = (transactionId: string) => postJson<Transaction>(`/transactions/${id(transactionId)}/recheck`);

export const reconcileTransaction = (transactionId: string, body: ReconcileRequest) =>
  postJson<Transaction>(`/transactions/${id(transactionId)}/manual-reconcile`, body);