# 관리자 권한 배정 화면의 열거형. 범위 유형은 스키마 SK 코드집합에 대응한다
from enum import StrEnum


class AssignmentScope(StrEnum):
    SYSTEM = "SYSTEM"  # SK.SYSTEM 전체 운영구조 (업무정보 조회 권한 없음)
    GROUP = "GROUP"  # SK.GROUP 운영묶음 전체
    DONG = "DONG"  # SK.DONG 행정동 하나


class AssignmentStatus(StrEnum):
    """배정 상태. 유효기간과 사용 여부(USE_YN)에서 서버가 정한다."""

    ACTIVE = "ACTIVE"  # 유효
    SCHEDULED = "SCHEDULED"  # 시작 전
    EXPIRED = "EXPIRED"  # 기간 종료
    REVOKED = "REVOKED"  # 회수됨 (USE_YN = N)
