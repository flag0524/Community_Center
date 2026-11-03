# 게시판 도메인의 열거형. 주소에 쓰는 게시판 키
from enum import StrEnum


class BoardKey(StrEnum):
    """게시판 7개. 게시판 설정(TB_BBS)의 유형(BT 코드집합)과 정책으로 구분하며 화면은 키로만 조회한다."""

    NOTICE = "notice"  # BT.NOTICE 공지사항
    NEWS = "news"  # BT.NOTICE 기관소식
    RESOURCES = "resources"  # BT.DATA 자료실
    GALLERY = "gallery"  # BT.GALLERY 센터 갤러리
    FAQ = "faq"  # BT.FAQ 자주하는 질문
    QNA = "qna"  # BT.QNA 질문과 답변
    REVIEW = "review"  # BT.REVIEW 수강후기


class InquiryStatus(StrEnum):
    """문의 처리 상태. 답변은 한 단계다(FN-053)."""

    RECEIVED = "RECEIVED"  # 접수
    ANSWERED = "ANSWERED"  # 답변완료
