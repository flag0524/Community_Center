# 관리자 감면 사전심사 화면의 열거형. 코드는 스키마 DR·DS 코드집합에 대응한다
from enum import StrEnum


class ReductionType(StrEnum):
    """감면 대상 3종. 조리읍 거주 확인 회원 본인만 대상이다(FN-038)."""

    LIVELIHOOD = "LIVELIHOOD"  # DR.LIVELIHD 기초생활보장 수급자 본인
    VETERAN = "VETERAN"  # DR.VETERAN 국가유공자 본인
    DISABLED = "DISABLED"  # DR.DISABLED 등록 장애인 본인


class ReductionStatus(StrEnum):
    RECEIVED = "RECEIVED"  # DS.RECEIVED 접수
    APPROVED = "APPROVED"  # DS.APPROVED 승인
    REJECTED = "REJECTED"  # DS.REJECTED 반려
    REVOKED = "REVOKED"  # DS.REVOKED 철회


class ReductionDecision(StrEnum):
    APPROVE = "APPROVE"  # DR.APPROVE 감면 승인
    REJECT = "REJECT"  # DR.REJECT 감면 반려
