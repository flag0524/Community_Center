// 개발 서버와 시험이 함께 쓰는 관리자 모의 API 처리기. 아직 만들지 않은 경로는 정의하지 않는다
import { applicationHandlers } from './applications';
import { attendanceHandlers } from './attendance';
import { authHandlers } from './auth';
import { boardHandlers } from './boards';
import { campusHandlers } from './campus';
import { contentHandlers } from './contents';
import { educationHandlers } from './education';
import { fileHandlers } from './files';
import { inquiryHandlers } from './inquiries';
import { memberHandlers } from './members';
import { refundHandlers } from './refunds';
import { reductionHandlers } from './reductions';
import { reviewHandlers } from './review';
import { roleHandlers } from './roles';
import { settingHandlers } from './settings';
import { smsHandlers } from './sms';
import { statsHandlers } from './stats';
import { termHandlers } from './terms';
import { transactionHandlers } from './transactions';

export const handlers = [...authHandlers, ...educationHandlers, ...campusHandlers, ...reviewHandlers, ...attendanceHandlers, ...applicationHandlers, ...transactionHandlers, ...refundHandlers, ...memberHandlers, ...boardHandlers, ...inquiryHandlers, ...contentHandlers, ...termHandlers, ...fileHandlers, ...statsHandlers, ...smsHandlers, ...roleHandlers, ...reductionHandlers, ...settingHandlers];