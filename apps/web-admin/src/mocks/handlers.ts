// 개발 서버와 시험이 함께 쓰는 관리자 모의 API 처리기. 아직 만들지 않은 경로는 정의하지 않는다
import { applicationHandlers } from './applications';
import { attendanceHandlers } from './attendance';
import { authHandlers } from './auth';
import { boardHandlers } from './boards';
import { campusHandlers } from './campus';
import { educationHandlers } from './education';
import { memberHandlers } from './members';
import { refundHandlers } from './refunds';
import { reviewHandlers } from './review';
import { transactionHandlers } from './transactions';

export const handlers = [...authHandlers, ...educationHandlers, ...campusHandlers, ...reviewHandlers, ...attendanceHandlers, ...applicationHandlers, ...transactionHandlers, ...refundHandlers, ...memberHandlers, ...boardHandlers];