// 결제 요청과 승인 확인 호출. 결제대행사(PG)는 계약 후 정해지므로 결제창을 여는 자리는 어댑터로 분리한다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';
import type { PaymentMethod } from './queries';

export type PaymentRequestResult = Schemas['PaymentRequestResult'];
export type PaymentConfirmResult = Schemas['PaymentConfirmResult'];

export const requestPayment = (applicationId: string, method: PaymentMethod, idempotencyKey: string) =>
  postJson<PaymentRequestResult>(
    `/me/applications/${encodeURIComponent(applicationId)}/payments`,
    { method },
    { headers: { 'Idempotency-Key': idempotencyKey } },
  );

export const confirmPayment = (body: { orderNo: string; paymentKey: string; amount: number }) =>
  postJson<PaymentConfirmResult>('/payments/confirm', body);

/**
 * 결제창에서 인증을 마치고 돌아온 결제 키. 실제 PG 연동 전에는 모의 결제창이 승인을 대신하므로 고정 값을 돌려준다.
 * PG가 정해지면 이 함수가 결제창을 열고 인증 결과의 결제 키를 돌려주도록 바꾼다.
 */
export async function openGatewayWindow(request: PaymentRequestResult): Promise<string> {
  return `mock-payment-key-${request.orderNo}`;
}
