# 개인식별 명단 내보내기의 열거형. 이름·연락처가 실제로 들어가는 목록만 대상이다
from enum import StrEnum


class PiiExportTarget(StrEnum):
    MEMBERS = "MEMBERS"  # 회원 목록 (AU.MBR_R 범위)
    APPLICATIONS = "APPLICATIONS"  # 수강신청 목록 (AU.APLY_R 범위)
