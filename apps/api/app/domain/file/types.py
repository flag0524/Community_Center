# 파일 도메인의 열거형(처리 상태·용도·소유 업무 종류). 관리자·주민 서비스가 함께 쓰며 이 도메인이 소유한다
from enum import StrEnum

FILE_URL = "/api/v1/files/{}"


def file_url(file_sn: int) -> str:
    """주민 화면이 파일을 받는 주소. 열어도 되는지는 받을 때 다시 판정한다."""
    return FILE_URL.format(file_sn)


class FileStatus(StrEnum):
    """파일 처리 상태. TB_FILE.FILE_STTS_CD(FS 코드집합)에 대응한다."""

    PENDING = "PENDING"  # FS.PENDING 검사 대기
    SAFE = "SAFE"  # FS.SAFE 검사 통과
    BLOCK = "BLOCK"  # FS.BLOCK 차단
    DELETE = "DELETE"  # FS.DELETE 삭제


class FilePurpose(StrEnum):
    """파일 용도. TB_FILE.FILE_USE_CD(FP 코드집합)에 대응한다."""

    ATTACH = "ATTACH"  # FP.ATTACH 첨부
    PLAN = "PLAN"  # FP.PLAN 강의계획서
    PROOF = "PROOF"  # FP.PROOF 증빙
    IMAGE = "IMAGE"  # FP.IMAGE 이미지


class FileOwnerKind(StrEnum):
    """파일 하나는 소유 업무 하나에만 속한다(FILE-10). 소유 업무의 접근 권한이 파일 접근 권한이다."""

    POST = "POST"  # 게시물
    COURSE = "COURSE"  # 강좌(강의계획서)
    INSTRUCTOR_APPLICATION = "INSTRUCTOR_APPLICATION"  # 강사 지원서·증빙
    CONTENT = "CONTENT"  # 홈·센터 콘텐츠
    APPLICATION = "APPLICATION"  # 수강신청
    REFUND = "REFUND"  # 환불 증빙
    REDUCTION = "REDUCTION"  # 감면 사전심사 증빙
    STATS_SOURCE = "STATS_SOURCE"  # 연령·성별 집계자료
    SATISFACTION_SOURCE = "SATISFACTION_SOURCE"  # 만족도 원자료
    FACILITY = "FACILITY"  # 시설·강의실 사진
