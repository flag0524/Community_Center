# 설계안 5.3의 서술형 무결성 규칙 중 DB 검사로 옮길 수 있게 문서가 분명히 적은 것을 CHECK 제약으로 정의한다
from dataclasses import dataclass

from app.tools.schema_doc import SchemaDoc


@dataclass(frozen=True)
class NarrativeCheck:
    rule_id: str  # 설계안 5.3의 규칙 번호
    table: str
    name: str  # 제약 이름의 뒷부분. 앞에 CK_<규칙>_이 붙는다
    expression: str
    columns: tuple[str, ...]  # 식이 읽는 컬럼. 문서에 있는지 검증한다

    @property
    def constraint(self) -> str:
        return f"CK_{self.rule_id.replace('-', '_')}_{self.name}"


def _c(rule_id: str, table: str, name: str, expression: str, *columns: str) -> NarrativeCheck:
    return NarrativeCheck(rule_id, table, name, expression, columns)


# 문서가 "DB CHECK"로 적었거나 DB 제약으로 분명히 서술한 것만 둔다. 환불 요청자 "정확히 하나"(R15)처럼
# 문서가 서비스 계층 규칙으로 분류한 것은 옮기지 않는다.
CURATED: tuple[NarrativeCheck, ...] = (
    _c("R01", "TB_COM_CD", "GROUP", "SUBSTRING_INDEX(COM_CD, '.', 1) = CD_GROUP_ID", "COM_CD", "CD_GROUP_ID"),
    _c(
        "R04",
        "TB_INSTR",
        "APPROVE",
        "INSTR_STTS_CD <> 'IS.APPROVE' OR (APRV_DT IS NOT NULL AND APRV_MNGR_SN IS NOT NULL)",
        "INSTR_STTS_CD",
        "APRV_DT",
        "APRV_MNGR_SN",
    ),
    _c("R05", "TB_EDU_CYCL", "NO", "EDU_CYCL >= 1", "EDU_CYCL"),
    _c("R05", "TB_EDU_CYCL", "EDU", "EDU_BGNG_YMD <= EDU_END_YMD", "EDU_BGNG_YMD", "EDU_END_YMD"),
    _c("R05", "TB_EDU_CYCL", "RCPT", "RCPT_BGNG_DT < RCPT_END_DT", "RCPT_BGNG_DT", "RCPT_END_DT"),
    _c(
        "R06",
        "TB_CORS",
        "NUM",
        "RCRT_NOPE > 0 AND WTNG_NOPE >= 0 AND TTCHG >= 0 AND STLM_WTNG_MINUTE > 0",
        "RCRT_NOPE",
        "WTNG_NOPE",
        "TTCHG",
        "STLM_WTNG_MINUTE",
    ),
    _c("R08", "TB_CORS_SCHDL", "TM", "BGNG_TM < END_TM", "BGNG_TM", "END_TM"),
    _c("R08", "TB_CORS_SCHDL", "YMD", "APLCN_BGNG_YMD <= APLCN_END_YMD", "APLCN_BGNG_YMD", "APLCN_END_YMD"),
    _c(
        "R09",
        "TB_ATNLC_APLY",
        "AMT",
        "TTCHG_AMT >= 0 AND RDCT_AMT >= 0 AND RDCT_AMT <= TTCHG_AMT"
        " AND STLM_PRNMNT_AMT = TTCHG_AMT - RDCT_AMT",
        "TTCHG_AMT",
        "RDCT_AMT",
        "STLM_PRNMNT_AMT",
    ),
    _c(
        "R09",
        "TB_ATNLC_APLY",
        "RSN",
        "RDCT_AMT = 0 OR (RDCT_RSN IS NOT NULL AND RDCT_MNGR_SN IS NOT NULL)",
        "RDCT_AMT",
        "RDCT_RSN",
        "RDCT_MNGR_SN",
    ),
    _c(
        "R10",
        "TB_ATNLC_APLY",
        "WAIT",
        "WTNG_SEQ IS NULL OR APLY_STTS_CD = 'ES.WAIT'",
        "WTNG_SEQ",
        "APLY_STTS_CD",
    ),
    _c(
        "R10",
        "TB_ATNLC_APLY",
        "HOLD",
        "APLY_STTS_CD <> 'ES.HOLD' OR STLM_DDLN_DT IS NOT NULL",
        "APLY_STTS_CD",
        "STLM_DDLN_DT",
    ),
    _c(
        "R10",
        "TB_ATNLC_APLY",
        "CANCEL",
        "APLY_STTS_CD <> 'ES.CANCEL' OR RTRCN_DT IS NOT NULL",
        "APLY_STTS_CD",
        "RTRCN_DT",
    ),
    _c(
        "SEAT-01",
        "TB_ATNLC_APLY",
        "WAIT",
        "APLY_STTS_CD <> 'ES.WAIT' OR (SEAT_ALTMNT_DT IS NULL AND STLM_DDLN_DT IS NULL)",
        "APLY_STTS_CD",
        "SEAT_ALTMNT_DT",
        "STLM_DDLN_DT",
    ),
    _c("R13", "TB_STLM", "AMT", "STLM_AMT > 0", "STLM_AMT"),
    _c(
        "R13",
        "TB_STLM",
        "PAID",
        "STLM_STTS_CD <> 'PS.PAID' OR STLM_APRV_DT IS NOT NULL",
        "STLM_STTS_CD",
        "STLM_APRV_DT",
    ),
    _c("R14", "TB_RFND", "AMT", "RFND_AMT > 0", "RFND_AMT"),
    _c(
        "RFND-01",
        "TB_RFND",
        "REJECT",
        "RFND_STTS_CD <> 'RS.REJECT' OR RJCT_RSN IS NOT NULL",
        "RFND_STTS_CD",
        "RJCT_RSN",
    ),
    _c(
        "RFND-01",
        "TB_RFND",
        "HOLD",
        "RFND_STTS_CD <> 'RS.HOLD' OR HLDOF_RSN IS NOT NULL",
        "RFND_STTS_CD",
        "HLDOF_RSN",
    ),
    _c(
        "R16",
        "TB_PST",
        "AUTHOR",
        "(WRT_MBR_SN IS NULL) <> (WRT_MNGR_SN IS NULL)",
        "WRT_MBR_SN",
        "WRT_MNGR_SN",
    ),
    _c(
        "R16",
        "TB_PST",
        "PARENT",
        "(PST_TYPE_CD = 'PT.POST' AND UP_PST_SN IS NULL)"
        " OR (PST_TYPE_CD = 'PT.REPLY' AND UP_PST_SN IS NOT NULL)",
        "PST_TYPE_CD",
        "UP_PST_SN",
    ),
    _c(
        "R18",
        "TB_FILE",
        "OWNER",
        "(PST_SN IS NOT NULL) + (CORS_SN IS NOT NULL) + (INSTR_SN IS NOT NULL) + (SITE_CONTS_SN IS NOT NULL)"
        " + (ATNLC_APLY_SN IS NOT NULL) + (RFND_SN IS NOT NULL) + (INSTR_APLY_SN IS NOT NULL)"
        " + (MBR_STATS_SRC_SN IS NOT NULL) + (RDCT_BFHD_SRNG_SN IS NOT NULL)"
        " + (CORS_DGSTFN_SRC_SN IS NOT NULL) = 1",
        "PST_SN",
        "CORS_SN",
        "INSTR_SN",
        "SITE_CONTS_SN",
        "ATNLC_APLY_SN",
        "RFND_SN",
        "INSTR_APLY_SN",
        "MBR_STATS_SRC_SN",
        "RDCT_BFHD_SRNG_SN",
        "CORS_DGSTFN_SRC_SN",
    ),
    _c(
        "R19",
        "TB_MNGR_SCP",
        "SCOPE",
        "(SCP_TYPE_CD = 'SK.SYSTEM' AND OPER_BNDL_SN IS NULL AND DONG_SN IS NULL)"
        " OR (SCP_TYPE_CD = 'SK.GROUP' AND OPER_BNDL_SN IS NOT NULL AND DONG_SN IS NULL)"
        " OR (SCP_TYPE_CD = 'SK.DONG' AND OPER_BNDL_SN IS NOT NULL AND DONG_SN IS NOT NULL)",
        "SCP_TYPE_CD",
        "OPER_BNDL_SN",
        "DONG_SN",
    ),
    _c(
        "R19",
        "TB_MNGR_SCP",
        "PERIOD",
        "VLD_END_DT IS NULL OR VLD_END_DT > VLD_BGNG_DT",
        "VLD_END_DT",
        "VLD_BGNG_DT",
    ),
    _c(
        "R21",
        "TB_JOB_HSTRY",
        "ACTOR",
        "(ACTR_TYPE_CD = 'AK.MEMBER' AND OPER_BNDL_SN IS NOT NULL AND MBR_SN IS NOT NULL)"
        " OR (ACTR_TYPE_CD = 'AK.ADMIN' AND MNGR_SN IS NOT NULL)"
        " OR (ACTR_TYPE_CD IN ('AK.SYSTEM', 'AK.ANON') AND MBR_SN IS NULL AND MNGR_SN IS NULL)",
        "ACTR_TYPE_CD",
        "OPER_BNDL_SN",
        "MBR_SN",
        "MNGR_SN",
    ),
    _c(
        "R21",
        "TB_JOB_HSTRY",
        "DONG",
        "DONG_SN IS NULL OR OPER_BNDL_SN IS NOT NULL",
        "DONG_SN",
        "OPER_BNDL_SN",
    ),
    _c(
        "RCRT-01",
        "TB_INSTR_RCRT",
        "PERIOD",
        "(RCRT_BGNG_DT IS NULL) = (RCRT_END_DT IS NULL)"
        " AND (RCRT_BGNG_DT IS NULL OR RCRT_BGNG_DT < RCRT_END_DT)",
        "RCRT_BGNG_DT",
        "RCRT_END_DT",
    ),
    _c("RCRT-01", "TB_INSTR_RCRT", "NOPE", "RCRT_NOPE IS NULL OR RCRT_NOPE > 0", "RCRT_NOPE"),
    _c("STAT-04", "TB_MBR_STATS_TOT", "NOPE", "TOT_NOPE >= 0", "TOT_NOPE"),
    _c(
        "STAT-04",
        "TB_MBR_STATS_TOT",
        "AGE",
        "LLMT_AGE IS NULL OR UPLMT_AGE IS NULL OR LLMT_AGE <= UPLMT_AGE",
        "LLMT_AGE",
        "UPLMT_AGE",
    ),
    _c(
        "SMS-02",
        "TB_SMS_DMND",
        "SOURCE",
        "(DMND_TYPE_CD <> 'SM.MANUAL' OR DMND_MNGR_SN IS NOT NULL)"
        " AND (DMND_TYPE_CD <> 'SM.AUTO' OR SRC_EVENT_ID IS NOT NULL)",
        "DMND_TYPE_CD",
        "DMND_MNGR_SN",
        "SRC_EVENT_ID",
    ),
    _c(
        "SMS-03", "TB_SMS_TRGT", "ONE", "(MBR_SN IS NULL) <> (CERT_DMND_SN IS NULL)", "MBR_SN", "CERT_DMND_SN"
    ),
    _c("AUTH-01", "TB_CERT_DMND", "ONE", "MBR_SN IS NULL OR MNGR_SN IS NULL", "MBR_SN", "MNGR_SN"),
)


def r27_checks(schema: SchemaDoc) -> list[NarrativeCheck]:
    """R27. 일련번호는 양의 정수, 정렬순서·횟수·인원은 0 이상이다. 컬럼 도메인으로 테이블마다 만든다."""
    checks: list[NarrativeCheck] = []
    for table in schema.tables:
        positive = [c.name for c in table.columns if c.domain.startswith("일련번호N22")]
        non_negative = [
            c.name for c in table.columns if c.domain.split("/")[0].strip() in ("순서N10", "수N10")
        ]
        suffix = table.name.removeprefix("TB_")
        if positive:
            expression = " AND ".join(f"({name} IS NULL OR {name} > 0)" for name in positive)
            checks.append(_c("R27", table.name, f"SN_{suffix}", expression, *positive))
        if non_negative:
            expression = " AND ".join(f"({name} IS NULL OR {name} >= 0)" for name in non_negative)
            checks.append(_c("R27", table.name, f"NUM_{suffix}", expression, *non_negative))
    return checks


def narrative_checks(schema: SchemaDoc) -> list[NarrativeCheck]:
    return [*CURATED, *r27_checks(schema)]


def problems(schema: SchemaDoc) -> list[str]:
    """식이 읽는 컬럼이 문서에 있고 식에 실제로 나오는지, 제약 이름이 겹치지 않고 64자 안인지 확인한다."""
    found: list[str] = []
    names: set[str] = set()
    for check in narrative_checks(schema):
        table = next((t for t in schema.tables if t.name == check.table), None)
        if table is None:
            found.append(f"{check.constraint}: 없는 테이블 {check.table}")
            continue
        existing = {column.name for column in table.columns}
        for column in check.columns:
            if column not in existing:
                found.append(f"{check.constraint}: 없는 컬럼 {column}")
            if column not in check.expression:
                found.append(f"{check.constraint}: 식에 {column}이 없음")
        if check.constraint in names:
            found.append(f"제약 이름 중복 {check.constraint}")
        names.add(check.constraint)
        if len(check.constraint) > 64:
            found.append(f"제약 이름이 64자를 넘음 {check.constraint}")
    return found
