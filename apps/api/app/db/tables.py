# 스키마 설계안에서 app.tools.generate_ddl이 만든 SQLAlchemy 테이블 정의. 직접 고치지 않는다
# 기본값(SERVER_NOW, 시퀀스 NEXTVAL)은 DB가 채우므로 여기에 두지 않는다. ZF_* 생성 컬럼도 뺐다.
from sqlalchemy import CHAR, Column, DateTime, MetaData, Numeric, String, Table, Text, text

metadata = MetaData()

TB_OPER_BNDL = Table(
    "TB_OPER_BNDL",
    metadata,
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_OPER_BNDL)"),
    ),
    Column(
        "OPER_BNDL_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "SITE_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "SITE_ID",
        String(40),
        nullable=False,
    ),
    Column(
        "URL_ADDR",
        String(2000),
        nullable=False,
    ),
    Column(
        "TELNO",
        String(11),
        nullable=True,
    ),
    Column(
        "ADDR",
        String(200),
        nullable=True,
    ),
    Column(
        "TMZN_NM",
        String(40),
        nullable=False,
    ),
    Column(
        "SORT_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_DONG = Table(
    "TB_DONG",
    metadata,
    Column(
        "DONG_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_DONG)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DONG_CD",
        CHAR(8),
        nullable=True,
    ),
    Column(
        "DONG_NM",
        String(40),
        nullable=False,
    ),
    Column(
        "SORT_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_COM_CD = Table(
    "TB_COM_CD",
    metadata,
    Column(
        "COM_CD",
        CHAR(12),
        primary_key=True,
        autoincrement=False,
    ),
    Column(
        "CD_GROUP_ID",
        String(20),
        nullable=False,
    ),
    Column(
        "CD_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "CD_EXPLN",
        String(4000),
        nullable=True,
    ),
    Column(
        "SORT_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
)

TB_MBR = Table(
    "TB_MBR",
    metadata,
    Column(
        "MBR_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_MBR)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DONG_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "LGN_ID",
        String(20),
        nullable=False,
    ),
    Column(
        "PSWD_HASH_VL",
        String(255),
        nullable=False,
    ),
    Column(
        "MBR_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "MBR_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "MBR_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "MBL_TELNO",
        String(11),
        nullable=True,
    ),
    Column(
        "EML_ADDR",
        String(320),
        nullable=True,
    ),
    Column(
        "MBR_JOIN_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "WHDWL_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCNT_LGN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "PSWD_FAIL_NMTM",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "LCK_END_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "HAB_RGN_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "HAB_IDNTY_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "HAB_IDNTY_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "HAB_IDNTY_MNS_CD",
        CHAR(12),
        nullable=True,
    ),
    Column(
        "HAB_IDNTY_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "HAB_IDNTY_BSS_ID",
        String(128),
        nullable=True,
    ),
)

TB_INSTR = Table(
    "TB_INSTR",
    metadata,
    Column(
        "INSTR_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_INSTR)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "MBR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "INSTR_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "INSTR_INTRO_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "CRR_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "QLFC_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "APLY_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "APRV_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "APRV_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "RJCT_RSN",
        String(4000),
        nullable=True,
    ),
    Column(
        "RLS_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_EDU_CYCL = Table(
    "TB_EDU_CYCL",
    metadata,
    Column(
        "EDU_CYCL_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_EDU_CYCL)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "EDU_YR",
        CHAR(4),
        nullable=False,
    ),
    Column(
        "EDU_CYCL",
        Numeric(3, 0),
        nullable=False,
    ),
    Column(
        "EDU_CYCL_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "EDU_BGNG_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "EDU_END_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "RCPT_BGNG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "RCPT_END_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_CORS = Table(
    "TB_CORS",
    metadata,
    Column(
        "CORS_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_CORS)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DONG_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "EDU_CYCL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "INSTR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "CORS_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "CORS_CLSF_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "CORS_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "RCRT_NOPE",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "WTNG_NOPE",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "TTCHG",
        Numeric(15, 0),
        nullable=False,
    ),
    Column(
        "RCPT_BGNG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "RCPT_END_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "EDU_BGNG_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "EDU_END_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "STLM_WTNG_MINUTE",
        Numeric(4, 0),
        nullable=False,
    ),
    Column(
        "LCTR_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "LCTR_PLAN_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "CORS_CLSF_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "OTSD_RGN_RCPT_BGNG_DT",
        DateTime(),
        nullable=True,
    ),
)

TB_CORS_SCHDL = Table(
    "TB_CORS_SCHDL",
    metadata,
    Column(
        "CORS_SCHDL_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_CORS_SCHDL)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "CORS_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "FCLT_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DOW_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "BGNG_TM",
        CHAR(6),
        nullable=False,
    ),
    Column(
        "END_TM",
        CHAR(6),
        nullable=False,
    ),
    Column(
        "APLCN_BGNG_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "APLCN_END_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_FCLT = Table(
    "TB_FCLT",
    metadata,
    Column(
        "FCLT_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_FCLT)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DONG_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "UP_FCLT_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "FCLT_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "FCLT_NM",
        String(256),
        nullable=False,
    ),
    Column(
        "ADDR",
        String(200),
        nullable=True,
    ),
    Column(
        "PSCP_NOPE",
        Numeric(10, 0),
        nullable=True,
    ),
    Column(
        "FCLT_EXPLN",
        String(4000),
        nullable=True,
    ),
    Column(
        "USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_ATNLC_APLY = Table(
    "TB_ATNLC_APLY",
    metadata,
    Column(
        "ATNLC_APLY_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_ATNLC_APLY)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "MBR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "CORS_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "APLY_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "APLY_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "WTNG_SEQ",
        Numeric(10, 0),
        nullable=True,
    ),
    Column(
        "TTCHG_AMT",
        Numeric(15, 0),
        nullable=False,
    ),
    Column(
        "RDCT_AMT",
        Numeric(15, 0),
        nullable=False,
    ),
    Column(
        "STLM_PRNMNT_AMT",
        Numeric(15, 0),
        nullable=False,
    ),
    Column(
        "RDCT_RSN",
        String(4000),
        nullable=True,
    ),
    Column(
        "RDCT_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "STLM_DDLN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RTRCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RTRCN_RSN",
        String(4000),
        nullable=True,
    ),
    Column(
        "IDEM_KEY",
        String(128),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "SEAT_ALTMNT_DT",
        DateTime(),
        nullable=True,
    ),
)

TB_STLM = Table(
    "TB_STLM",
    metadata,
    Column(
        "STLM_SN",
        Numeric(10, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_STLM)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "ATNLC_APLY_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "STLM_NO",
        String(20),
        nullable=False,
    ),
    Column(
        "PG_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "FRCS_ID",
        String(128),
        nullable=False,
    ),
    Column(
        "PG_DLNG_ID",
        String(128),
        nullable=True,
    ),
    Column(
        "STLM_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "STLM_MNS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "STLM_AMT",
        Numeric(15, 0),
        nullable=False,
    ),
    Column(
        "IDEM_KEY",
        String(128),
        nullable=False,
    ),
    Column(
        "STLM_DMND_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "STLM_APRV_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "STLM_APRV_NO",
        String(50),
        nullable=True,
    ),
    Column(
        "STLM_EXPRY_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "FAIL_CD",
        String(40),
        nullable=True,
    ),
    Column(
        "FAIL_RSN",
        String(4000),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_RFND = Table(
    "TB_RFND",
    metadata,
    Column(
        "RFND_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_RFND)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "STLM_SN",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "RFND_AMT",
        Numeric(15, 0),
        nullable=False,
    ),
    Column(
        "RFND_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "RFND_RSN",
        String(4000),
        nullable=False,
    ),
    Column(
        "RFND_DMND_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "DMND_MBR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "DMND_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "APRV_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "APRV_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RFND_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "PG_RFND_ID",
        String(128),
        nullable=True,
    ),
    Column(
        "IDEM_KEY",
        String(128),
        nullable=False,
    ),
    Column(
        "RFND_BANK_CD",
        String(20),
        nullable=True,
    ),
    Column(
        "RFND_ACTNO_ENCPT_VL",
        String(1024),
        nullable=True,
    ),
    Column(
        "RFND_DPSTR_ENCPT_VL",
        String(1024),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "IMPL_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "IMPL_DMND_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RJCT_RSN",
        String(4000),
        nullable=True,
    ),
    Column(
        "HLDOF_RSN",
        String(4000),
        nullable=True,
    ),
)

TB_BBS = Table(
    "TB_BBS",
    metadata,
    Column(
        "BBS_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_BBS)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "BBS_ID",
        String(40),
        nullable=False,
    ),
    Column(
        "BBS_NM",
        String(256),
        nullable=False,
    ),
    Column(
        "BBS_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "MBR_WRT_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "ANS_USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "ATCH_USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "SORT_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_PST = Table(
    "TB_PST",
    metadata,
    Column(
        "PST_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_PST)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DONG_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "BBS_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "UP_PST_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "PST_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "PST_TTL",
        String(256),
        nullable=False,
    ),
    Column(
        "PST_CN",
        Text(),
        nullable=False,
    ),
    Column(
        "WRT_MBR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "WRT_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "PRVT_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "NTC_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "DEL_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "PSTG_BGNG_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "PSTG_END_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "CORS_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "INQRY_CLSF_CD",
        CHAR(12),
        nullable=True,
    ),
)

TB_FILE = Table(
    "TB_FILE",
    metadata,
    Column(
        "FILE_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_FILE)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "PST_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "CORS_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "INSTR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "SITE_CONTS_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "ATNLC_APLY_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "RFND_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "FILE_NM",
        String(300),
        nullable=False,
    ),
    Column(
        "STRG_KEY",
        String(300),
        nullable=False,
    ),
    Column(
        "MIME_TYPE_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "FILE_SZ",
        Numeric(14, 0),
        nullable=False,
    ),
    Column(
        "FILE_HASH_VL",
        CHAR(64),
        nullable=False,
    ),
    Column(
        "FILE_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "FILE_USE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "SORT_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "INSTR_APLY_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "MBR_STATS_SRC_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "RDCT_BFHD_SRNG_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "CORS_DGSTFN_SRC_SN",
        Numeric(22, 0),
        nullable=True,
    ),
)

TB_SITE_CONTS = Table(
    "TB_SITE_CONTS",
    metadata,
    Column(
        "SITE_CONTS_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_SITE_CONTS)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DONG_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "CONTS_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "CONTS_ID",
        String(40),
        nullable=False,
    ),
    Column(
        "CONTS_TTL",
        String(256),
        nullable=False,
    ),
    Column(
        "CONTS_CN",
        Text(),
        nullable=False,
    ),
    Column(
        "VER_NM",
        String(40),
        nullable=False,
    ),
    Column(
        "CONTS_HASH_VL",
        CHAR(64),
        nullable=True,
    ),
    Column(
        "URL_ADDR",
        String(2000),
        nullable=True,
    ),
    Column(
        "PSTG_BGNG_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "PSTG_END_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "PSTG_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "ESNTL_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "SORT_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "RVW_STTS_CD",
        CHAR(12),
        nullable=True,
    ),
)

TB_MNGR = Table(
    "TB_MNGR",
    metadata,
    Column(
        "MNGR_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_MNGR)"),
    ),
    Column(
        "LGN_ID",
        String(20),
        nullable=False,
    ),
    Column(
        "PSWD_HASH_VL",
        String(255),
        nullable=False,
    ),
    Column(
        "MNGR_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "EML_ADDR",
        String(320),
        nullable=True,
    ),
    Column(
        "MBL_TELNO",
        String(11),
        nullable=True,
    ),
    Column(
        "USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "RCNT_LGN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "PSWD_FAIL_NMTM",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "LCK_END_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_MNGR_ROLE = Table(
    "TB_MNGR_ROLE",
    metadata,
    Column(
        "ROLE_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_MNGR_ROLE)"),
    ),
    Column(
        "ROLE_ID",
        String(40),
        nullable=False,
    ),
    Column(
        "ROLE_NM",
        String(300),
        nullable=False,
    ),
    Column(
        "ROLE_EXPLN",
        String(4000),
        nullable=True,
    ),
    Column(
        "USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_MNGR_SCP = Table(
    "TB_MNGR_SCP",
    metadata,
    Column(
        "MNGR_SCP_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_MNGR_SCP)"),
    ),
    Column(
        "MNGR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "ROLE_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "SCP_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "DONG_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "VLD_BGNG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "VLD_END_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "GRNT_MNGR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_JOB_HSTRY = Table(
    "TB_JOB_HSTRY",
    metadata,
    Column(
        "JOB_HSTRY_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_JOB_HSTRY)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "DONG_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "ACTR_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "MBR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "JOB_CD",
        String(40),
        nullable=False,
    ),
    Column(
        "TRGT_TBL_NM",
        String(300),
        nullable=False,
    ),
    Column(
        "TRGT_KEY_VL",
        String(100),
        nullable=True,
    ),
    Column(
        "JOB_RSLT_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "DMND_ID",
        String(128),
        nullable=False,
    ),
    Column(
        "CNTN_IP_ADDR",
        String(45),
        nullable=True,
    ),
    Column(
        "CHG_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
)

TB_ROLE_AUTHRT = Table(
    "TB_ROLE_AUTHRT",
    metadata,
    Column(
        "ROLE_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
    ),
    Column(
        "AUTHRT_CD",
        CHAR(12),
        primary_key=True,
        autoincrement=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
)

TB_MBR_AGRE_HSTRY = Table(
    "TB_MBR_AGRE_HSTRY",
    metadata,
    Column(
        "MBR_AGRE_HSTRY_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_MBR_AGRE_HSTRY)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "MBR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "SITE_CONTS_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "AGRE_ACT_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "AGRE_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "CONTS_HASH_VL",
        CHAR(64),
        nullable=False,
    ),
    Column(
        "IDEM_KEY",
        String(128),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
)

TB_STLM_EVENT = Table(
    "TB_STLM_EVENT",
    metadata,
    Column(
        "STLM_EVENT_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_STLM_EVENT)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "STLM_SN",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "RFND_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "EVENT_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "EVENT_ID",
        String(128),
        nullable=False,
    ),
    Column(
        "PRCS_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "EVENT_HASH_VL",
        CHAR(64),
        nullable=False,
    ),
    Column(
        "EVENT_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "RCPTN_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "PRCS_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RTRY_NMTM",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "FAIL_RSN",
        String(4000),
        nullable=True,
    ),
)

TB_RDCT_HSTRY = Table(
    "TB_RDCT_HSTRY",
    metadata,
    Column(
        "RDCT_HSTRY_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_RDCT_HSTRY)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "ATNLC_APLY_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DCSN_RSLT_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "RDCT_AMT",
        Numeric(15, 0),
        nullable=True,
    ),
    Column(
        "DCSN_RSN",
        String(4000),
        nullable=True,
    ),
    Column(
        "DCSN_MNGR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DCSN_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "RDCT_BFHD_SRNG_SN",
        Numeric(22, 0),
        nullable=True,
    ),
)

TB_RDCT_HSTRY_FILE = Table(
    "TB_RDCT_HSTRY_FILE",
    metadata,
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
    ),
    Column(
        "RDCT_HSTRY_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
    ),
    Column(
        "FILE_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
)

TB_CORS_ATND = Table(
    "TB_CORS_ATND",
    metadata,
    Column(
        "ATND_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_CORS_ATND)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "CORS_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "CORS_SCHDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "INSTR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "LCTR_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "LCTR_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "ATND_NOPE",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "ABSNC_NOPE",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "UNCHCK_NOPE",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "CMPTN_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "MEMO_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "IDEM_KEY",
        String(128),
        nullable=False,
    ),
    Column(
        "DEL_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "DEL_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "CORS_SCHDL_CHG_SN",
        Numeric(22, 0),
        nullable=True,
    ),
)

TB_CORS_ATND_DTL = Table(
    "TB_CORS_ATND_DTL",
    metadata,
    Column(
        "ATND_DTL_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_CORS_ATND_DTL)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "ATND_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "ATNLC_APLY_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "ATND_RSLT_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_CORS_ATND_HSTRY = Table(
    "TB_CORS_ATND_HSTRY",
    metadata,
    Column(
        "ATND_HSTRY_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_CORS_ATND_HSTRY)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "ATND_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "ATND_DTL_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "ACTR_INSTR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "ACTN_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "BFR_VL_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "AFTR_VL_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "TRGT_RCRD_VER",
        Numeric(10, 0),
        nullable=True,
    ),
    Column(
        "DMND_ID",
        String(128),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
)

TB_CORS_SCHDL_CHG = Table(
    "TB_CORS_SCHDL_CHG",
    metadata,
    Column(
        "CORS_SCHDL_CHG_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_CORS_SCHDL_CHG)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "CORS_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "CORS_SCHDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "ORGNL_LCTR_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "CHG_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "CHG_LCTR_YMD",
        CHAR(8),
        nullable=True,
    ),
    Column(
        "CHG_BGNG_TM",
        CHAR(6),
        nullable=True,
    ),
    Column(
        "CHG_END_TM",
        CHAR(6),
        nullable=True,
    ),
    Column(
        "CHG_FCLT_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "CHG_RSN",
        String(4000),
        nullable=False,
    ),
    Column(
        "REG_MNGR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "APLCN_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_INSTR_RCRT = Table(
    "TB_INSTR_RCRT",
    metadata,
    Column(
        "INSTR_RCRT_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_INSTR_RCRT)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "PST_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "RCRT_BGNG_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRT_END_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRT_NOPE",
        Numeric(10, 0),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_SMS_DMND = Table(
    "TB_SMS_DMND",
    metadata,
    Column(
        "SMS_DMND_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_SMS_DMND)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DMND_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "DMND_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "TRGT_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "DSPTCH_TELNO",
        String(11),
        nullable=False,
    ),
    Column(
        "SMS_CN",
        Text(),
        nullable=False,
    ),
    Column(
        "IDEM_KEY",
        String(128),
        nullable=False,
    ),
    Column(
        "DMND_HASH_VL",
        CHAR(64),
        nullable=False,
    ),
    Column(
        "SRC_EVENT_ID",
        String(128),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
)

TB_SMS_DMND_CORS = Table(
    "TB_SMS_DMND_CORS",
    metadata,
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
    ),
    Column(
        "SMS_DMND_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
    ),
    Column(
        "CORS_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
)

TB_SMS_TRGT = Table(
    "TB_SMS_TRGT",
    metadata,
    Column(
        "SMS_TRGT_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_SMS_TRGT)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "SMS_DMND_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "MBR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "RCPTN_TELNO_ENCPT_VL",
        String(1024),
        nullable=False,
    ),
    Column(
        "TRGT_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "CERT_DMND_SN",
        Numeric(22, 0),
        nullable=True,
    ),
)

TB_SMS_SNDNG_HSTRY = Table(
    "TB_SMS_SNDNG_HSTRY",
    metadata,
    Column(
        "SMS_SNDNG_HSTRY_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_SMS_SNDNG_HSTRY)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "SMS_TRGT_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "SNDNG_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "SPLR_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "SPLR_ACNT_ID",
        String(128),
        nullable=False,
    ),
    Column(
        "SPLR_MSG_ID",
        String(128),
        nullable=True,
    ),
    Column(
        "IDEM_KEY",
        String(128),
        nullable=False,
    ),
    Column(
        "PRCS_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "SNDNG_DMND_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "RSLT_IDNTY_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "FAIL_CD",
        String(40),
        nullable=True,
    ),
    Column(
        "FAIL_RSN",
        String(4000),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_INSTR_APLY = Table(
    "TB_INSTR_APLY",
    metadata,
    Column(
        "INSTR_APLY_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_INSTR_APLY)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "INSTR_RCRT_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "RCPT_CHNL_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "MBR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "APLCT_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "TELNO_ENCPT_VL",
        String(1024),
        nullable=False,
    ),
    Column(
        "HOPE_CORS_NM",
        String(200),
        nullable=False,
    ),
    Column(
        "HOPE_FLD_NM",
        String(200),
        nullable=True,
    ),
    Column(
        "CRR_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "INSTR_INTRO_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "RLS_HOPE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "SBMSN_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "RCPT_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "SRNG_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "SRNG_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "SRNG_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RJCT_RSN",
        String(4000),
        nullable=True,
    ),
    Column(
        "INSTR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "IDEM_KEY",
        String(128),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_MBR_STATS_SRC = Table(
    "TB_MBR_STATS_SRC",
    metadata,
    Column(
        "MBR_STATS_SRC_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_MBR_STATS_SRC)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DONG_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "EDU_CYCL_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "CORS_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "SRC_NM",
        String(200),
        nullable=False,
    ),
    Column(
        "SRC_BSS_ID",
        String(200),
        nullable=False,
    ),
    Column(
        "DATST_ID",
        String(128),
        nullable=False,
    ),
    Column(
        "SRC_VER",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "BGNG_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "END_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "CRTR_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "TOT_CRTR_CN",
        String(4000),
        nullable=False,
    ),
    Column(
        "APRV_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "APRV_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "APRV_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_MBR_STATS_TOT = Table(
    "TB_MBR_STATS_TOT",
    metadata,
    Column(
        "MBR_STATS_TOT_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_MBR_STATS_TOT)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "MBR_STATS_SRC_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "AGE_GROUP_ID",
        String(40),
        nullable=False,
    ),
    Column(
        "AGE_GROUP_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "LLMT_AGE",
        Numeric(10, 0),
        nullable=True,
    ),
    Column(
        "UPLMT_AGE",
        Numeric(10, 0),
        nullable=True,
    ),
    Column(
        "GNDR_CLSF_ID",
        String(40),
        nullable=False,
    ),
    Column(
        "GNDR_CLSF_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "TOT_NOPE",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "SORT_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
)

TB_CERT_DMND = Table(
    "TB_CERT_DMND",
    metadata,
    Column(
        "CERT_DMND_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_CERT_DMND)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "MBR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "CERT_DMND_ID",
        String(128),
        nullable=False,
    ),
    Column(
        "CERT_PRPS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "TELNO_ENCPT_VL",
        String(1024),
        nullable=True,
    ),
    Column(
        "OTP_HASH_VL",
        String(255),
        nullable=False,
    ),
    Column(
        "KEY_VER_ID",
        String(40),
        nullable=False,
    ),
    Column(
        "EXPRY_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "CERT_USE_CMPTN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "FAIL_NMTM",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "IDEM_KEY",
        String(128),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_LGN_FAIL_HSTRY = Table(
    "TB_LGN_FAIL_HSTRY",
    metadata,
    Column(
        "LGN_FAIL_HSTRY_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_LGN_FAIL_HSTRY)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "MBR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "FAIL_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "DMND_ID",
        String(128),
        nullable=False,
    ),
)

TB_LGN_SSN = Table(
    "TB_LGN_SSN",
    metadata,
    Column(
        "LGN_SSN_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_LGN_SSN)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "MBR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "TKN_HASH_VL",
        CHAR(64),
        nullable=False,
    ),
    Column(
        "ISSU_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "LAST_ACT_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "EXPRY_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "DSCD_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "DSCD_RSN",
        String(200),
        nullable=True,
    ),
    Column(
        "ADD_CERT_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_CORS_CLSF = Table(
    "TB_CORS_CLSF",
    metadata,
    Column(
        "CORS_CLSF_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_CORS_CLSF)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "CORS_CLSF_NM",
        String(100),
        nullable=False,
    ),
    Column(
        "CLSF_NM_KEY",
        String(128),
        nullable=False,
    ),
    Column(
        "SORT_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "USE_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "DEL_YN",
        CHAR(1),
        nullable=False,
    ),
    Column(
        "REG_MNGR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DEL_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_CORS_DGSTFN_SRC = Table(
    "TB_CORS_DGSTFN_SRC",
    metadata,
    Column(
        "CORS_DGSTFN_SRC_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_CORS_DGSTFN_SRC)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "CORS_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "DATST_ID",
        String(128),
        nullable=False,
    ),
    Column(
        "SRC_VER",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "SRC_NM",
        String(200),
        nullable=False,
    ),
    Column(
        "SRC_BSS_ID",
        String(200),
        nullable=False,
    ),
    Column(
        "BGNG_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "END_YMD",
        CHAR(8),
        nullable=False,
    ),
    Column(
        "RSPNS_NOPE",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "TOT_CRTR_CN",
        String(4000),
        nullable=False,
    ),
    Column(
        "APRV_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "APRV_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "APRV_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "REG_MNGR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TB_CORS_DGSTFN_QITEM = Table(
    "TB_CORS_DGSTFN_QITEM",
    metadata,
    Column(
        "CORS_DGSTFN_QITEM_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_CORS_DGSTFN_QITEM)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "CORS_DGSTFN_SRC_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "QITEM_ID",
        String(40),
        nullable=False,
    ),
    Column(
        "QITEM_NM",
        String(300),
        nullable=False,
    ),
    Column(
        "RSPNS_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "RSPNS_NOPE",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "LLMT_SCR",
        Numeric(15, 6),
        nullable=True,
    ),
    Column(
        "UPLMT_SCR",
        Numeric(15, 6),
        nullable=True,
    ),
    Column(
        "TOT_CRTR_CN",
        String(4000),
        nullable=False,
    ),
    Column(
        "SORT_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
)

TB_CORS_DGSTFN_TOT = Table(
    "TB_CORS_DGSTFN_TOT",
    metadata,
    Column(
        "CORS_DGSTFN_TOT_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_CORS_DGSTFN_TOT)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "CORS_DGSTFN_QITEM_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "ARTCL_ID",
        String(40),
        nullable=False,
    ),
    Column(
        "ARTCL_NM",
        String(200),
        nullable=False,
    ),
    Column(
        "RSPNS_NOPE",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "SCR",
        Numeric(15, 6),
        nullable=True,
    ),
    Column(
        "SORT_SEQ",
        Numeric(10, 0),
        nullable=False,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
)

TB_RDCT_BFHD_SRNG = Table(
    "TB_RDCT_BFHD_SRNG",
    metadata,
    Column(
        "RDCT_BFHD_SRNG_SN",
        Numeric(22, 0),
        primary_key=True,
        autoincrement=False,
        server_default=text("NEXTVAL(SQ_RDCT_BFHD_SRNG)"),
    ),
    Column(
        "OPER_BNDL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "MBR_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "EDU_CYCL_SN",
        Numeric(22, 0),
        nullable=False,
    ),
    Column(
        "RDCT_TYPE_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "SRNG_STTS_CD",
        CHAR(12),
        nullable=False,
    ),
    Column(
        "APLY_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "SRNG_MNGR_SN",
        Numeric(22, 0),
        nullable=True,
    ),
    Column(
        "SRNG_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "SRNG_CN",
        String(4000),
        nullable=True,
    ),
    Column(
        "RJCT_RSN",
        String(4000),
        nullable=True,
    ),
    Column(
        "VLD_END_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "REG_DT",
        DateTime(),
        nullable=False,
    ),
    Column(
        "MDFCN_DT",
        DateTime(),
        nullable=True,
    ),
    Column(
        "RCRD_VER",
        Numeric(10, 0),
        nullable=False,
    ),
)

TABLE_NAMES = (
    "TB_OPER_BNDL",
    "TB_DONG",
    "TB_COM_CD",
    "TB_MBR",
    "TB_INSTR",
    "TB_EDU_CYCL",
    "TB_CORS",
    "TB_CORS_SCHDL",
    "TB_FCLT",
    "TB_ATNLC_APLY",
    "TB_STLM",
    "TB_RFND",
    "TB_BBS",
    "TB_PST",
    "TB_FILE",
    "TB_SITE_CONTS",
    "TB_MNGR",
    "TB_MNGR_ROLE",
    "TB_MNGR_SCP",
    "TB_JOB_HSTRY",
    "TB_ROLE_AUTHRT",
    "TB_MBR_AGRE_HSTRY",
    "TB_STLM_EVENT",
    "TB_RDCT_HSTRY",
    "TB_RDCT_HSTRY_FILE",
    "TB_CORS_ATND",
    "TB_CORS_ATND_DTL",
    "TB_CORS_ATND_HSTRY",
    "TB_CORS_SCHDL_CHG",
    "TB_INSTR_RCRT",
    "TB_SMS_DMND",
    "TB_SMS_DMND_CORS",
    "TB_SMS_TRGT",
    "TB_SMS_SNDNG_HSTRY",
    "TB_INSTR_APLY",
    "TB_MBR_STATS_SRC",
    "TB_MBR_STATS_TOT",
    "TB_CERT_DMND",
    "TB_LGN_FAIL_HSTRY",
    "TB_LGN_SSN",
    "TB_CORS_CLSF",
    "TB_CORS_DGSTFN_SRC",
    "TB_CORS_DGSTFN_QITEM",
    "TB_CORS_DGSTFN_TOT",
    "TB_RDCT_BFHD_SRNG",
)
