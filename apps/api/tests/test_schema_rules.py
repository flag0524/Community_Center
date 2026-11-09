# 서술형 무결성 규칙(R01·R04·R05·R06·R08·R09·R10·R13·R14·R16·R18·R19·R21·R27 등)을 어기는 행을 실제 DB에 넣어 그 제약이 막는지 확인하는 시험
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError

from app.tools.schema_checks import CURATED
from app.tools.schema_doc import SchemaDoc, parse_schema_doc
from tests.factory import RowFactory

pytestmark = pytest.mark.db

LATER = "2026-01-01 00:10:00"


@pytest.fixture(scope="module")
def schema() -> SchemaDoc:
    return parse_schema_doc()


@pytest.fixture()
def conn(migrated_engine: Engine) -> Iterator[Connection]:
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture()
def factory(conn: Connection, schema: SchemaDoc) -> RowFactory:
    return RowFactory(conn, schema)


# (표, 위반 값, 막아야 하는 제약 이름). 값이 없는 컬럼은 도구의 기본값을 쓴다.
VIOLATIONS: list[tuple[str, dict[str, Any], str]] = [
    ("TB_COM_CD", {"COM_CD": "ZY.A", "CD_GROUP_ID": "ZX"}, "CK_R01_GROUP"),
    ("TB_INSTR", {"INSTR_STTS_CD": "IS.APPROVE"}, "CK_R04_APPROVE"),
    ("TB_EDU_CYCL", {"EDU_CYCL": 0}, "CK_R05_NO"),
    ("TB_EDU_CYCL", {"EDU_BGNG_YMD": "20260301", "EDU_END_YMD": "20260101"}, "CK_R05_EDU"),
    (
        "TB_EDU_CYCL",
        {"RCPT_BGNG_DT": "2026-03-01 00:00:00", "RCPT_END_DT": "2026-02-01 00:00:00"},
        "CK_R05_RCPT",
    ),
    ("TB_EDU_CYCL", {"RCPT_BGNG_DT": LATER, "RCPT_END_DT": LATER}, "CK_R05_RCPT"),  # 시작과 종료가 같다
    ("TB_CORS", {"RCRT_NOPE": 0}, "CK_R06_NUM"),
    ("TB_CORS", {"WTNG_NOPE": -1}, "CK_R06_NUM"),
    ("TB_CORS", {"TTCHG": -1}, "CK_R06_NUM"),
    ("TB_CORS", {"STLM_WTNG_MINUTE": 0}, "CK_R06_NUM"),
    ("TB_CORS_SCHDL", {"BGNG_TM": "100000", "END_TM": "090000"}, "CK_R08_TM"),
    ("TB_CORS_SCHDL", {"BGNG_TM": "090000", "END_TM": "090000"}, "CK_R08_TM"),  # 시작 = 종료는 불가
    ("TB_CORS_SCHDL", {"APLCN_BGNG_YMD": "20260301", "APLCN_END_YMD": "20260101"}, "CK_R08_YMD"),
    ("TB_ATNLC_APLY", {"TTCHG_AMT": 10, "RDCT_AMT": 20, "STLM_PRNMNT_AMT": -10}, "CK_R09_AMT"),
    (
        "TB_ATNLC_APLY",
        {"TTCHG_AMT": 10, "RDCT_AMT": 3, "STLM_PRNMNT_AMT": 10},
        "CK_R09_AMT",
    ),  # 결제예정액 = 수강료 - 감면
    (
        "TB_ATNLC_APLY",
        {"TTCHG_AMT": 10, "RDCT_AMT": 3, "STLM_PRNMNT_AMT": 7},
        "CK_R09_RSN",
    ),  # 감면은 사유·관리자 필수
    ("TB_ATNLC_APLY", {"APLY_STTS_CD": "ES.HOLD", "WTNG_SEQ": 3, "STLM_DDLN_DT": LATER}, "CK_R10_WAIT"),
    ("TB_ATNLC_APLY", {"APLY_STTS_CD": "ES.HOLD"}, "CK_R10_HOLD"),
    ("TB_ATNLC_APLY", {"APLY_STTS_CD": "ES.CANCEL"}, "CK_R10_CANCEL"),
    ("TB_ATNLC_APLY", {"APLY_STTS_CD": "ES.WAIT", "SEAT_ALTMNT_DT": LATER}, "CK_SEAT_01_WAIT"),
    ("TB_STLM", {"STLM_AMT": 0}, "CK_R13_AMT"),
    ("TB_STLM", {"STLM_STTS_CD": "PS.PAID"}, "CK_R13_PAID"),
    ("TB_RFND", {"RFND_AMT": 0}, "CK_R14_AMT"),
    ("TB_RFND", {"RFND_STTS_CD": "RS.REJECT"}, "CK_RFND_01_REJECT"),
    ("TB_RFND", {"RFND_STTS_CD": "RS.HOLD"}, "CK_RFND_01_HOLD"),
    ("TB_PST", {"WRT_MNGR_SN": None}, "CK_R16_AUTHOR"),  # 작성자가 없다
    ("TB_PST", {"PST_TYPE_CD": "PT.REPLY"}, "CK_R16_PARENT"),  # 답변에 원글이 없다
    ("TB_FILE", {"PST_SN": None}, "CK_R18_OWNER"),  # 소유자가 없다
    ("TB_MNGR_SCP", {"SCP_TYPE_CD": "SK.GROUP"}, "CK_R19_SCOPE"),  # 묶음 범위인데 묶음이 없다
    ("TB_MNGR_SCP", {"SCP_TYPE_CD": "SK.DONG"}, "CK_R19_SCOPE"),
    (
        "TB_MNGR_SCP",
        {"VLD_BGNG_DT": "2026-01-01 00:00:00", "VLD_END_DT": "2025-01-01 00:00:00"},
        "CK_R19_PERIOD",
    ),
    ("TB_JOB_HSTRY", {"ACTR_TYPE_CD": "AK.ADMIN"}, "CK_R21_ACTOR"),
    ("TB_JOB_HSTRY", {"ACTR_TYPE_CD": "AK.MEMBER"}, "CK_R21_ACTOR"),
    ("TB_INSTR_RCRT", {"RCRT_BGNG_DT": "2026-01-01 00:00:00"}, "CK_RCRT_01_PERIOD"),  # 한쪽만 입력
    ("TB_INSTR_RCRT", {"RCRT_BGNG_DT": LATER, "RCRT_END_DT": LATER}, "CK_RCRT_01_PERIOD"),  # 시작 = 종료
    ("TB_INSTR_RCRT", {"RCRT_NOPE": 0}, "CK_RCRT_01_NOPE"),
    ("TB_MBR_STATS_TOT", {"TOT_NOPE": -1}, "CK_STAT_04_NOPE"),
    ("TB_MBR_STATS_TOT", {"LLMT_AGE": 50, "UPLMT_AGE": 10}, "CK_STAT_04_AGE"),
    ("TB_SMS_DMND", {"DMND_TYPE_CD": "SM.AUTO"}, "CK_SMS_02_SOURCE"),  # 자동 알림에 원업무사건 식별자가 없다
    ("TB_SMS_DMND", {"DMND_MNGR_SN": None}, "CK_SMS_02_SOURCE"),  # 관리자 문자에 요청관리자가 없다
    ("TB_SMS_TRGT", {"MBR_SN": None}, "CK_SMS_03_ONE"),  # 회원도 인증요청도 없다
    ("TB_OPER_BNDL", {"SORT_SEQ": -1}, "CK_R27_NUM_OPER_BNDL"),
    ("TB_OPER_BNDL", {"OPER_BNDL_SN": 0}, "CK_R27_SN_OPER_BNDL"),
]


@pytest.mark.parametrize(("table", "values", "constraint"), VIOLATIONS, ids=lambda v: str(v)[:60])
def test_규칙을_어기는_행은_해당_제약이_막는다(
    factory: RowFactory, table: str, values: dict[str, Any], constraint: str
) -> None:
    with pytest.raises(DBAPIError) as caught:
        factory.make(table, **values)
    assert caught.value.orig is not None
    assert caught.value.orig.args[0] == 4025
    assert f"`{constraint}`" in str(caught.value.orig.args[1])


def test_검사_제약마다_위반_사례가_하나_이상_있다(schema: SchemaDoc) -> None:
    """새 규칙을 더하고 시험을 빠뜨리지 않게 한다. R27은 표마다 자동 생성이라 대표 두 건만 둔다."""
    covered = {constraint for _, _, constraint in VIOLATIONS} | {
        "CK_AUTH_01_ONE",
        "CK_R21_DONG",
    }  # 아래 별도 시험
    curated = {check.constraint for check in CURATED}
    assert curated - covered == set(), sorted(curated - covered)


def test_회원과_관리자를_동시에_연결한_인증요청은_막는다(conn: Connection, factory: RowFactory) -> None:
    member = factory.make("TB_MBR")
    manager = factory.make("TB_MNGR")
    base = factory.make("TB_CERT_DMND", MBR_SN=member["MBR_SN"], OPER_BNDL_SN=member["OPER_BNDL_SN"])
    with pytest.raises(DBAPIError) as both:
        conn.execute(
            text("UPDATE TB_CERT_DMND SET MNGR_SN = :m WHERE CERT_DMND_SN = :s"),
            {"m": manager["MNGR_SN"], "s": base["CERT_DMND_SN"]},
        )
    assert both.value.orig is not None
    assert "`CK_AUTH_01_ONE`" in str(both.value.orig.args[1])


def test_파일에_소유자가_둘이면_막는다(factory: RowFactory) -> None:
    course = factory.make("TB_CORS")
    post = factory.make(
        "TB_PST", OPER_BNDL_SN=course["OPER_BNDL_SN"]
    )  # 두 번째 소유자를 시험이 직접 지정한다
    with pytest.raises(DBAPIError) as two:
        factory.make(
            "TB_FILE",
            CORS_SN=course["CORS_SN"],
            PST_SN=post["PST_SN"],
            OPER_BNDL_SN=course["OPER_BNDL_SN"],
        )
    assert two.value.orig is not None
    assert "`CK_R18_OWNER`" in str(two.value.orig.args[1])


def test_작업이력은_동이_있는데_묶음이_없으면_막는다(conn: Connection, factory: RowFactory) -> None:
    """도구는 외래키 때문에 묶음까지 채우므로, 만든 뒤 묶음만 비워 위반 상태를 만든다."""
    row = factory.make("TB_JOB_HSTRY")
    with pytest.raises(DBAPIError) as caught:
        conn.execute(
            text("UPDATE TB_JOB_HSTRY SET DONG_SN = 1 WHERE JOB_HSTRY_SN = :s"),
            {"s": row["JOB_HSTRY_SN"]},
        )
    assert caught.value.orig is not None
    # 묶음이 비어 있는 상태에서 동을 넣으면 CK_R21_DONG이 막는다. 외래키 검사는 묶음이 NULL이면 건너뛴다.
    assert "`CK_R21_DONG`" in str(caught.value.orig.args[1])


def test_시스템_범위는_묶음이_있으면_막는다(factory: RowFactory) -> None:
    with pytest.raises(DBAPIError) as caught:
        factory.make("TB_MNGR_SCP", SCP_TYPE_CD="SK.SYSTEM", OPER_BNDL_SN=factory.bundle())
    assert caught.value.orig is not None
    assert "`CK_R19_SCOPE`" in str(caught.value.orig.args[1])


def test_시스템_행위자_작업이력에_회원이_있으면_막는다(factory: RowFactory) -> None:
    member = factory.make("TB_MBR")
    with pytest.raises(DBAPIError) as caught:
        factory.make(
            "TB_JOB_HSTRY",
            ACTR_TYPE_CD="AK.SYSTEM",
            OPER_BNDL_SN=member["OPER_BNDL_SN"],
            MBR_SN=member["MBR_SN"],
        )
    assert caught.value.orig is not None
    assert "`CK_R21_ACTOR`" in str(caught.value.orig.args[1])


def test_올바른_값은_통과한다(factory: RowFactory) -> None:
    """위반 시험이 우연히 모든 값을 막는 제약 때문에 통과하지 않는다는 반대편 증거."""
    factory.make("TB_EDU_CYCL", EDU_BGNG_YMD="20260101", EDU_END_YMD="20260101")  # 같은 날은 허용
    factory.make(
        "TB_ATNLC_APLY",
        TTCHG_AMT=10,
        RDCT_AMT=3,
        STLM_PRNMNT_AMT=7,
        RDCT_RSN="저소득",
        RDCT_MNGR_SN=factory.make("TB_MNGR")["MNGR_SN"],
    )
    factory.make("TB_INSTR_RCRT", RCRT_BGNG_DT="2026-01-01 00:00:00", RCRT_END_DT=LATER, RCRT_NOPE=5)
    factory.make("TB_MBR_STATS_TOT", LLMT_AGE=10, UPLMT_AGE=10)  # 경계 같음 허용
    factory.make("TB_MNGR_SCP", SCP_TYPE_CD="SK.GROUP", OPER_BNDL_SN=factory.bundle())
    factory.make(
        "TB_JOB_HSTRY",
        ACTR_TYPE_CD="AK.MEMBER",
        OPER_BNDL_SN=factory.bundle(),
        MBR_SN=factory.make("TB_MBR")["MBR_SN"],
    )
