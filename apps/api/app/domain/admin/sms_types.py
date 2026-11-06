# 관리자 알림 이력과 문자 발송 화면의 열거형. 코드는 스키마 SM·SG·SS 코드집합에 대응한다
from enum import StrEnum


class SmsKind(StrEnum):
    AUTO = "AUTO"  # SM.AUTO 자동 업무알림
    MANUAL = "MANUAL"  # SM.MANUAL 관리자 문자


class SmsScope(StrEnum):
    CENTER = "CENTER"  # SG.CENTER 센터 전체
    COURSE = "COURSE"  # SG.COURSE 선택 강좌
    EVENT = "EVENT"  # SG.EVENT 업무사건 대상 (자동 알림)


class SmsTargetState(StrEnum):
    """수신 대상별 처리 상태. TB_SMS_TRGT.TRGT_STTS_CD(SS 코드집합)에 대응한다."""

    WAIT = "WAIT"  # SS.WAIT 발송대기
    SENDING = "SENDING"  # SS.SENDING 요청중
    SENT = "SENT"  # SS.SENT 공급자가 최종 성공 확인
    FAIL = "FAIL"  # SS.FAIL 실패 확인
    UNKNOWN = "UNKNOWN"  # SS.UNKNOWN 결과확인중
    SKIP = "SKIP"  # SS.SKIP 발송 제외


class SmsAudienceStatus(StrEnum):
    """관리자 발송의 수신 대상을 고르는 수강신청 상태. 대상 산정에만 쓰고 요청에는 저장하지 않는다."""

    CONFIRMED = "CONFIRMED"  # 수강확정
    PAYMENT_PENDING = "PAYMENT_PENDING"  # 결제대기
    WAITING = "WAITING"  # 대기
