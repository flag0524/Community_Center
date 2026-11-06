# 관리자 문의 답변과 홈·센터 콘텐츠 화면의 열거형
from enum import StrEnum


class ContentType(StrEnum):
    """홈·센터 콘텐츠 유형. TB_SITE_CONTS.CONTS_TYPE_CD(CT 코드집합)에 대응한다.

    BANNER·POPUP·HISTORY·INTRO는 스키마에 있는 코드다. VISUAL·CONTACT·GUIDE·FACILITY는 스키마 개정 요청서
    (R9·R14)의 제안 코드이며 개정이 확정되기 전까지 모의 서버에서만 쓴다.
    """

    VISUAL = "VISUAL"  # 홈 비주얼 (제안)
    BANNER = "BANNER"  # CT.BANNER 배너
    POPUP = "POPUP"  # CT.POPUP 팝업
    HISTORY = "HISTORY"  # CT.HISTORY 연혁
    INTRO = "INTRO"  # CT.INTRO 센터소개
    CONTACT = "CONTACT"  # 연락처 (제안, PRD Q23)
    GUIDE = "GUIDE"  # 수강·환불 안내 (제안 CT.GUIDE)
    FACILITY = "FACILITY"  # 시설안내 (제안 CT.FACILITY)


class AnswerAction(StrEnum):
    CREATED = "CREATED"  # 답변 작성
    EDITED = "EDITED"  # 답변 수정
