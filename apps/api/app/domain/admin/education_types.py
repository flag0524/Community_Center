# 관리자 교육 운영 화면의 열거형. 강좌 관리 상태와 교육기수 상태
from enum import StrEnum


class CourseAdminStatus(StrEnum):
    """관리자가 정하는 강좌 상태. 접수·교육 상태는 이 값과 별개로 서버가 기간으로 판정한다(FN-057)."""

    DRAFT = "DRAFT"  # 작성중
    PUBLISHED = "PUBLISHED"  # 공개
    RECEPTION_CLOSED = "RECEPTION_CLOSED"  # 접수마감(수동)
    CANCELLED = "CANCELLED"  # 폐강


class CycleStatus(StrEnum):
    DRAFT = "DRAFT"  # 작성중
    ACTIVE = "ACTIVE"  # 사용중
    INACTIVE = "INACTIVE"  # 사용중지


class FacilityKind(StrEnum):
    CENTER = "CENTER"  # 센터
    ROOM = "ROOM"  # 강의실


class ScheduleChangeKind(StrEnum):
    CANCEL = "CANCEL"  # 휴강
    MAKEUP = "MAKEUP"  # 보강
