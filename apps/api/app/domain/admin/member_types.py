# 관리자 회원 조회 화면의 열거형. 회원 상태(MS 코드집합)와 검토 기록 구분
from enum import StrEnum


class MemberStatus(StrEnum):
    """회원 상태. TB_MBR.MBR_STTS_CD(MS 코드집합)에 대응한다."""

    ACTIVE = "ACTIVE"  # MS.ACTIVE 정상
    LOCKED = "LOCKED"  # MS.LOCKED 잠금
    WITHDRAWN = "WITHDRAWN"  # MS.WITHDRAW 탈퇴


class MemberReviewKind(StrEnum):
    """관리자가 남기는 검토 기록. 회원 정보를 바꾸지 않고 사유만 기록한다(FN-065)."""

    RESTRICT = "RESTRICT"  # 이용제한 검토
    WITHDRAW = "WITHDRAW"  # 탈퇴 검토
    NAME_CHANGE = "NAME_CHANGE"  # 이름 변경 요청 검토


class MemberReviewState(StrEnum):
    OPEN = "OPEN"  # 검토 중
    CLOSED = "CLOSED"  # 처리 완료
