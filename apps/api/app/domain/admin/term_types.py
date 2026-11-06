# 관리자 약관·동의문 버전 관리와 첨부파일 조회 화면의 열거형
from enum import StrEnum


class TermStatus(StrEnum):
    """약관·동의문 버전 상태. 확정되면 문안 해시가 고정되고 게시되면 덮어쓰지 않는다(FN-055, R17)."""

    REVIEW = "REVIEW"  # 검토 (작성 중, 수정 가능)
    FIXED = "FIXED"  # 확정 (문안 해시 고정, 수정 불가)
    PUBLISHED = "PUBLISHED"  # 게시 (현재 주민에게 보이는 버전)
    ENDED = "ENDED"  # 게시 종료 (새 버전이 게시되어 물러남)


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
    STATS_SOURCE = "STATS_SOURCE"  # 통계 집계자료
