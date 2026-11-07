# 관리자 강좌분류 화면의 열거형. 변경 이력은 작업이력(TB_JOB_HSTRY)에 쌓는다 (CLSF-03)
from enum import StrEnum


class ClassHistoryAction(StrEnum):
    CREATE = "CREATE"  # 등록
    RENAME = "RENAME"  # 명칭 변경
    REORDER = "REORDER"  # 순서 변경
    DEACTIVATE = "DEACTIVATE"  # 비활성
    ACTIVATE = "ACTIVATE"  # 재활성
    DELETE = "DELETE"  # 논리삭제
