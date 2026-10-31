// 생성된 타입이 일련번호를 문자열로 유지하는지 컴파일 시점에 검사한다. 어긋나면 tsc가 실패한다.
import type { Schemas } from './index';

type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;
type Assert<T extends true> = T;

export type SerialIdsAreStrings = [
  Assert<Equal<Schemas['ApplicationCreate']['courseId'], string>>,
  Assert<Equal<Schemas['Application']['applicationId'], string>>,
  Assert<Equal<Schemas['CourseSummary']['courseId'], string>>,
  Assert<Equal<Schemas['PaymentRequestResult']['paymentId'], string>>,
  Assert<Equal<Schemas['Refund']['refundId'], string>>,
];

// 금액은 숫자, 신청 요청에는 금액 필드가 없다.
export type MoneyIsNumber = Assert<Equal<Schemas['ApplicationSummary']['payableAmount'], number>>;
export type ApplicationCreateHasOnlyCourseId = Assert<Equal<keyof Schemas['ApplicationCreate'], 'courseId'>>;
