# 관리자 기능권한(AU) 코드. 스키마 6절의 코드집합에서 비활성인 AU.MBR_W를 뺀 것이다
from enum import StrEnum


class AdminAuthority(StrEnum):
    """화면은 이 코드를 해석하지 않고 서버가 준 메뉴만 그린다. 모든 요청은 서버가 다시 판정한다(FN-056)."""

    GRP_R = "AU.GRP_R"
    GRP_W = "AU.GRP_W"
    DONG_W = "AU.DONG_W"
    CONF_W = "AU.CONF_W"
    MBR_R = "AU.MBR_R"
    INSTR_W = "AU.INSTR_W"
    CORS_R = "AU.CORS_R"
    CORS_W = "AU.CORS_W"
    APLY_R = "AU.APLY_R"
    APLY_W = "AU.APLY_W"
    STLM_R = "AU.STLM_R"
    STLM_W = "AU.STLM_W"
    RFND_A = "AU.RFND_A"
    RFND_X = "AU.RFND_X"
    BBS_W = "AU.BBS_W"
    POST_W = "AU.POST_W"
    SITE_W = "AU.SITE_W"
    FCLT_W = "AU.FCLT_W"
    MNGR_W = "AU.MNGR_W"
    GRANT_W = "AU.GRANT_W"
    ROLE_W = "AU.ROLE_W"
    LOG_R = "AU.LOG_R"
    EXPORT = "AU.EXPORT"
    SMS_SEND = "AU.SMS_SEND"
    STAT_R = "AU.STAT_R"
    ATND_R = "AU.ATND_R"
