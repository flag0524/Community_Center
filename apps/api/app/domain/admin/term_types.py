# 관리자 약관·동의문 버전 관리의 열거형
from enum import StrEnum


class TermStatus(StrEnum):
    """약관·동의문 버전 상태. 확정되면 문안 해시가 고정되고 게시되면 덮어쓰지 않는다(FN-055, R17)."""

    REVIEW = "REVIEW"  # 검토 (작성 중, 수정 가능)
    FIXED = "FIXED"  # 확정 (문안 해시 고정, 수정 불가)
    PUBLISHED = "PUBLISHED"  # 게시 (현재 주민에게 보이는 버전)
    ENDED = "ENDED"  # 게시 종료 (새 버전이 게시되어 물러남)
