# 회원 도메인의 열거형. OTP 목적과 약관 유형
from enum import StrEnum


class OtpPurpose(StrEnum):
    """본인확인 목적. AP.JOIN, AP.ID_FIND, AP.PSWD, AP.PHONE에 대응하고 AP.ADMIN은 쓰지 않는다."""

    JOIN = "JOIN"
    ID_FIND = "ID_FIND"
    PASSWORD_RESET = "PASSWORD_RESET"
    PHONE_CHANGE = "PHONE_CHANGE"


class TermType(StrEnum):
    """약관·동의문 유형. 개인정보처리방침과 이메일무단수집거부는 CT 코드가 없어 스키마 개정 대기다."""

    TERMS_OF_USE = "TERMS_OF_USE"
    PRIVACY_CONSENT = "PRIVACY_CONSENT"
    MARKETING_CONSENT = "MARKETING_CONSENT"
    PRIVACY_POLICY = "PRIVACY_POLICY"
    EMAIL_REFUSAL = "EMAIL_REFUSAL"
