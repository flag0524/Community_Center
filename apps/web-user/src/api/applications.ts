// 수강신청 생성 요청. 같은 신청 시도는 같은 멱등키를 써서 서버가 중복 접수하지 않게 한다
import { postJson } from './http';
import type { Application } from './queries';

export const createApplication = (courseId: string, idempotencyKey: string) =>
  postJson<Application>('/me/applications', { courseId }, { headers: { 'Idempotency-Key': idempotencyKey } });

export const cancelApplication = (applicationId: string) =>
  postJson<Application>(`/me/applications/${encodeURIComponent(applicationId)}/cancel`);
