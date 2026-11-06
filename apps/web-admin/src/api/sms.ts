// 문자 발송 요청. 미리보기는 저장하지 않고 발송은 멱등키를 싣는다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type SmsAudience = Schemas['SmsAudience'];
export type SmsPreview = Schemas['SmsPreview'];
export type SmsRequestDetail = Schemas['SmsRequestDetail'];
export type SmsSendRequest = Schemas['SmsSendRequest'];

export const previewSms = (body: SmsAudience) => postJson<SmsPreview>('/sms/preview', body);
export const sendSms = (body: SmsSendRequest, key: string) => postJson<SmsRequestDetail>('/sms', body, { headers: { 'Idempotency-Key': key } });