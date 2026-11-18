# 강좌 만족도 집계자료 등록·목록·상세·승인·반려(권한은 연령·성별 집계자료와 같은 임시 매핑, ADR-091)
from datetime import date, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, scope_for
from app.core.errors import ApiError, ErrorCode
from app.core.times import utc
from app.db.tables import (
    TB_CORS,
    TB_CORS_DGSTFN_QITEM,
    TB_CORS_DGSTFN_SRC,
    TB_CORS_DGSTFN_TOT,
    TB_MNGR,
    TB_OPER_BNDL,
)
from app.domain.admin.satisfaction_input_schemas import (
    OptionView,
    QuestionView,
    ResponseType,
    SatisfactionSourceCreate,
    SatisfactionSourceDetail,
    SatisfactionSourceList,
    SatisfactionSourceSummary,
)
from app.domain.admin.stats_input_schemas import SourceState
from app.domain.admin.stats_input_service import DECIDE, REGISTER, mark_of, replayed

CREATE_JOB = "SATISFACTION_SRC_CREATE"
DECIDE_JOB = "SATISFACTION_SRC_DECIDE"
STATE = {
    "SA.DRAFT": SourceState.WAIT,
    "SA.APPROVED": SourceState.APPROVED,
    "SA.REJECTED": SourceState.REJECTED,
}
TYPE_CODE = {ResponseType.SINGLE: "DQ.SINGLE", ResponseType.MULTI: "DQ.MULTI", ResponseType.SCORE: "DQ.SCORE"}
CODE_TYPE = {code: kind for kind, code in TYPE_CODE.items()}
LIST_LIMIT = 100


def _ymd(value: date) -> str:
    return value.strftime("%Y%m%d")


def _date(value: Any) -> date | None:
    text = None if value is None else str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def _whole_viewer(db: Session, admin: Admin, now: datetime) -> None:
    if not any(scope_for(db, admin, code, now, group_only=True).whole for code in (REGISTER, DECIDE)):
        raise ApiError(ErrorCode.FORBIDDEN)


def _query() -> Any:
    return (
        select(TB_CORS_DGSTFN_SRC, TB_CORS.c.CORS_NM, TB_MNGR.c.MNGR_NM)
        .select_from(TB_CORS_DGSTFN_SRC)
        .join(
            TB_CORS,
            (TB_CORS.c.OPER_BNDL_SN == TB_CORS_DGSTFN_SRC.c.OPER_BNDL_SN)
            & (TB_CORS.c.CORS_SN == TB_CORS_DGSTFN_SRC.c.CORS_SN),
        )
        .outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_CORS_DGSTFN_SRC.c.APRV_MNGR_SN)
    )


def _summary(row: Any) -> SatisfactionSourceSummary:
    return SatisfactionSourceSummary(
        source_id=str(int(row.CORS_DGSTFN_SRC_SN)),
        course_id=str(int(row.CORS_SN)),
        course_name=str(row.CORS_NM),
        dataset_id=str(row.DATST_ID),
        version=int(row.SRC_VER),
        provider=str(row.SRC_NM),
        period_start=_date(row.BGNG_YMD),
        period_end=_date(row.END_YMD),
        respondents=int(row.RSPNS_NOPE),
        state=STATE[str(row.APRV_STTS_CD).strip()],
        registered_at=utc(row.REG_DT),
        decided_at=None if row.APRV_DT is None else utc(row.APRV_DT),
        decided_by=None if row.MNGR_NM is None else str(row.MNGR_NM),
    )


def list_sources(db: Session, admin: Admin, *, now: datetime) -> SatisfactionSourceList:
    _whole_viewer(db, admin, now)
    rows = db.execute(
        _query()
        .where(TB_CORS_DGSTFN_SRC.c.OPER_BNDL_SN == admin.bundle_sn)
        .order_by(TB_CORS_DGSTFN_SRC.c.CORS_DGSTFN_SRC_SN.desc())
        .limit(LIST_LIMIT)
    ).all()
    return SatisfactionSourceList(items=[_summary(r) for r in rows])


def _detail(db: Session, bundle: int, source_sn: int) -> SatisfactionSourceDetail:
    row = db.execute(
        _query().where(
            TB_CORS_DGSTFN_SRC.c.OPER_BNDL_SN == bundle, TB_CORS_DGSTFN_SRC.c.CORS_DGSTFN_SRC_SN == source_sn
        )
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    questions: list[QuestionView] = []
    for q in db.execute(
        select(TB_CORS_DGSTFN_QITEM)
        .where(TB_CORS_DGSTFN_QITEM.c.CORS_DGSTFN_SRC_SN == source_sn)
        .order_by(TB_CORS_DGSTFN_QITEM.c.SORT_SEQ, TB_CORS_DGSTFN_QITEM.c.CORS_DGSTFN_QITEM_SN)
    ):
        options = db.execute(
            select(TB_CORS_DGSTFN_TOT)
            .where(TB_CORS_DGSTFN_TOT.c.CORS_DGSTFN_QITEM_SN == q.CORS_DGSTFN_QITEM_SN)
            .order_by(TB_CORS_DGSTFN_TOT.c.SORT_SEQ, TB_CORS_DGSTFN_TOT.c.CORS_DGSTFN_TOT_SN)
        ).all()
        questions.append(
            QuestionView(
                question_id=str(q.QITEM_ID),
                name=str(q.QITEM_NM),
                type=CODE_TYPE[str(q.RSPNS_TYPE_CD).strip()],
                respondents=int(q.RSPNS_NOPE),
                min_score=q.LLMT_SCR,
                max_score=q.UPLMT_SCR,
                criteria=str(q.TOT_CRTR_CN),
                options=[
                    OptionView(
                        option_id=str(o.ARTCL_ID), name=str(o.ARTCL_NM), count=int(o.RSPNS_NOPE), score=o.SCR
                    )
                    for o in options
                ],
            )
        )
    return SatisfactionSourceDetail(
        **_summary(row).model_dump(),
        basis_id=str(row.SRC_BSS_ID),
        criteria=str(row.TOT_CRTR_CN),
        questions=questions,
    )


def get_source(db: Session, admin: Admin, *, now: datetime, source_id: str) -> SatisfactionSourceDetail:
    _whole_viewer(db, admin, now)
    return _detail(db, admin.bundle_sn, int(source_id))


def _validate(db: Session, bundle: int, body: SatisfactionSourceCreate) -> None:
    if body.period_end < body.period_start:
        raise _fail("periodEnd", "조사 기간의 끝은 시작보다 빠를 수 없습니다.")
    found = db.execute(
        select(TB_CORS.c.CORS_SN).where(
            TB_CORS.c.OPER_BNDL_SN == bundle, TB_CORS.c.CORS_SN == int(body.course_id)
        )
    ).first()
    if found is None:
        raise _fail("courseId", "이 센터에 없는 강좌입니다.")
    seen_questions: set[str] = set()
    for index, question in enumerate(body.questions):
        field = f"questions[{index}]"
        if question.question_id in seen_questions:
            raise _fail(field, "같은 문항 식별자가 두 번 들어 있습니다.")
        seen_questions.add(question.question_id)
        if question.respondents > body.respondents:
            raise _fail(field, "문항 유효응답자 수는 전체 응답자 수보다 클 수 없습니다.")
        is_score = question.type is ResponseType.SCORE
        low, high = question.min_score, question.max_score
        if is_score and (low is None or high is None or low > high):
            raise _fail(field, "점수 문항은 최소·최대 점수를 모두 입력하고 최소가 최대보다 클 수 없습니다.")
        if not is_score and (low is not None or high is not None):
            raise _fail(field, "점수 문항이 아니면 최소·최대 점수를 입력하지 않습니다.")
        seen_options: set[str] = set()
        for option in question.options:
            if option.option_id in seen_options:
                raise _fail(field, "같은 선택 항목 식별자가 두 번 들어 있습니다.")
            seen_options.add(option.option_id)
            if option.score is not None and not is_score:
                raise _fail(field, "점수 문항이 아니면 선택 항목에 점수를 입력하지 않습니다.")
            if (
                option.score is not None
                and low is not None
                and high is not None
                and not low <= option.score <= high
            ):
                raise _fail(field, "선택 항목의 점수가 최소·최대 점수 범위를 벗어났습니다.")
        total = sum(o.count for o in question.options)
        if question.type is ResponseType.MULTI:
            if any(o.count > question.respondents for o in question.options):
                raise _fail(field, "복수선택의 각 선택 수는 문항 유효응답자 수보다 클 수 없습니다.")
        elif (
            total != question.respondents
        ):  # 단일선택·점수는 선택 수의 합이 유효응답자 수와 같아야 한다(DGSTFN-02)
            raise _fail(field, "선택 수의 합이 문항 유효응답자 수와 같아야 합니다.")


def create_source(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    body: SatisfactionSourceCreate,
    idem_key: str,
) -> SatisfactionSourceDetail:
    """검토 전(SA.DRAFT)으로 등록한다. 버전은 강좌·계열마다 서버가 정하고 묶음 행 잠금으로 직렬화한다."""
    if not scope_for(db, admin, REGISTER, now, group_only=True).whole:
        raise ApiError(ErrorCode.FORBIDDEN)
    bundle = admin.bundle_sn
    _validate(db, bundle, body)
    db.execute(
        select(TB_OPER_BNDL.c.OPER_BNDL_SN).where(TB_OPER_BNDL.c.OPER_BNDL_SN == bundle).with_for_update()
    )
    mark = mark_of(idem_key, body)
    again = replayed(db, bundle, admin.admin_sn, mark, CREATE_JOB)
    if again is not None:
        return _detail(db, bundle, again)
    latest = db.execute(
        select(TB_CORS_DGSTFN_SRC.c.SRC_VER)
        .where(
            TB_CORS_DGSTFN_SRC.c.OPER_BNDL_SN == bundle,
            TB_CORS_DGSTFN_SRC.c.CORS_SN == int(body.course_id),
            TB_CORS_DGSTFN_SRC.c.DATST_ID == body.dataset_id,
        )
        .order_by(TB_CORS_DGSTFN_SRC.c.SRC_VER.desc())
        .limit(1)
    ).scalar()
    version = 1 if latest is None else int(latest) + 1
    source_sn = int(
        db.execute(
            insert(TB_CORS_DGSTFN_SRC)
            .values(
                OPER_BNDL_SN=bundle,
                CORS_SN=int(body.course_id),
                DATST_ID=body.dataset_id,
                SRC_VER=version,
                SRC_NM=body.provider,
                SRC_BSS_ID=body.basis_id,
                BGNG_YMD=_ymd(body.period_start),
                END_YMD=_ymd(body.period_end),
                RSPNS_NOPE=body.respondents,
                TOT_CRTR_CN=body.criteria,
                APRV_STTS_CD="SA.DRAFT",
                REG_MNGR_SN=admin.admin_sn,
                REG_DT=now,
            )
            .returning(TB_CORS_DGSTFN_SRC.c.CORS_DGSTFN_SRC_SN)
        ).scalar_one()
    )
    for q_index, question in enumerate(body.questions):
        question_sn = int(
            db.execute(
                insert(TB_CORS_DGSTFN_QITEM)
                .values(
                    OPER_BNDL_SN=bundle,
                    CORS_DGSTFN_SRC_SN=source_sn,
                    QITEM_ID=question.question_id,
                    QITEM_NM=question.name,
                    RSPNS_TYPE_CD=TYPE_CODE[question.type],
                    RSPNS_NOPE=question.respondents,
                    LLMT_SCR=question.min_score,
                    UPLMT_SCR=question.max_score,
                    TOT_CRTR_CN=question.criteria,
                    SORT_SEQ=q_index,
                    REG_DT=now,
                )
                .returning(TB_CORS_DGSTFN_QITEM.c.CORS_DGSTFN_QITEM_SN)
            ).scalar_one()
        )
        db.execute(
            insert(TB_CORS_DGSTFN_TOT),
            [
                {
                    "OPER_BNDL_SN": bundle,
                    "CORS_DGSTFN_QITEM_SN": question_sn,
                    "ARTCL_ID": option.option_id,
                    "ARTCL_NM": option.name,
                    "RSPNS_NOPE": option.count,
                    "SCR": option.score,
                    "SORT_SEQ": o_index,
                    "REG_DT": now,
                }
                for o_index, option in enumerate(question.options)
            ],
        )
    record_job(
        db,
        actor="AK.ADMIN",
        job=CREATE_JOB,
        table="TB_CORS_DGSTFN_SRC",
        key=source_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle,
        admin_sn=admin.admin_sn,
        change=f"등록 버전 {version} 문항 {len(body.questions)}건 {mark}",
    )
    return _detail(db, bundle, source_sn)


def _decide(
    db: Session, admin: Admin, *, now: datetime, request_id: str, source_id: str, status: str, label: str
) -> SatisfactionSourceDetail:
    if not scope_for(db, admin, DECIDE, now, group_only=True).whole:
        raise ApiError(ErrorCode.FORBIDDEN)
    bundle, source_sn = admin.bundle_sn, int(source_id)
    where = (
        TB_CORS_DGSTFN_SRC.c.OPER_BNDL_SN == bundle,
        TB_CORS_DGSTFN_SRC.c.CORS_DGSTFN_SRC_SN == source_sn,
    )
    current = db.execute(select(TB_CORS_DGSTFN_SRC.c.APRV_STTS_CD).where(*where).with_for_update()).first()
    if current is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    if str(current.APRV_STTS_CD).strip() != "SA.DRAFT":  # 이미 결정한 자료는 다시 결정하지 않는다
        raise ApiError(ErrorCode.CONFLICT_STATE, "검토 전 상태의 자료만 승인하거나 반려할 수 있습니다.")
    db.execute(
        update(TB_CORS_DGSTFN_SRC)
        .where(*where)
        .values(
            APRV_STTS_CD=status,
            APRV_MNGR_SN=admin.admin_sn,
            APRV_DT=now,
            MDFCN_DT=now,
            RCRD_VER=TB_CORS_DGSTFN_SRC.c.RCRD_VER + 1,
        )
    )
    record_job(
        db,
        actor="AK.ADMIN",
        job=DECIDE_JOB,
        table="TB_CORS_DGSTFN_SRC",
        key=source_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle,
        admin_sn=admin.admin_sn,
        change=label,
    )
    return _detail(db, bundle, source_sn)


def approve_source(
    db: Session, admin: Admin, *, now: datetime, request_id: str, source_id: str
) -> SatisfactionSourceDetail:
    return _decide(
        db, admin, now=now, request_id=request_id, source_id=source_id, status="SA.APPROVED", label="승인"
    )


def reject_source(
    db: Session, admin: Admin, *, now: datetime, request_id: str, source_id: str
) -> SatisfactionSourceDetail:
    return _decide(
        db, admin, now=now, request_id=request_id, source_id=source_id, status="SA.REJECTED", label="반려"
    )
