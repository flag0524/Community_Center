// 개발 서버와 시험이 함께 쓰는 관리자 모의 API 처리기. 아직 만들지 않은 경로는 정의하지 않는다
import { authHandlers } from './auth';
import { educationHandlers } from './education';

export const handlers = [...authHandlers, ...educationHandlers];