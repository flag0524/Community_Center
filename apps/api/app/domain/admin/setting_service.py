# 관리자 운영 설정(읽기 전용)과 공통 코드(표시명·순서·사용 여부). 코드값은 서버 업무 규칙이 쓰므로 바꾸지 않는다(FN-058, FN-069, PRD Q21, 개정 요청 R20, ADR-071)
import json
from datetime import datetime
from typing import Any

from sqlalchemy import Select, exists, func, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, permit
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_BBS,
    TB_COM_CD,
    TB_CORS,
    TB_FILE,
    TB_INSTR,
    TB_INSTR_APLY,
    TB_MBR,
    TB_PST,
    TB_RDCT_BFHD_SRNG,
    TB_RFND,
    TB_SITE_CONTS,
    TB_SMS_DMND,
    TB_SMS_TRGT,
    TB_STLM,
)
from app.domain.admin.setting_schemas import (
    CodeGroup,
    CodeGroupList,
    CodeList,
    CodeRow,
    CodeUpdate,
    SettingDetail,
    SettingPage,
    SettingSummary,
)
from app.domain.admin.setting_types import OperRuleStatus
from app.domain.admin.types import AdminAuthority as AU

OPER_RULE = "CT.OPER_RULE"
RULE_STATUS = {
    "OR.REVIEW": OperRuleStatus.REVIEW,
    "OR.DECIDED": OperRuleStatus.DECIDED,
    "OR.HOLD": OperRuleStatus.HOLD,
}
STATUS_CODE = {status: code for code, status in RULE_STATUS.items()}
SUMMARY_CHARS = 80

# 그룹 이름은 스키마 문서의 코드집합 이름과 코드 값의 뜻에서 옮겼다
GROUP_NAMES = {
    "AA": "동의 행위",
    "AH": "출석 변경 유형",
    "AK": "작업 주체 유형",
    "AP": "인증 목적",
    "AR": "출석 결과",
    "AU": "기능 권한",
    "BT": "게시판 유형",
    "CC": "강좌 분야(예시)",
    "CS": "강좌 상태",
    "CT": "콘텐츠 유형",
    "DQ": "만족도 응답 유형",
    "DR": "감면 판정·대상",
    "DS": "감면 사전심사 상태",
    "DW": "요일",
    "EP": "이벤트 처리 상태",
    "ES": "수강신청 상태",
    "ET": "결제 이벤트 유형",
    "FP": "파일 용도",
    "FS": "파일 처리 상태",
    "FT": "시설 유형",
    "IA": "강사 지원 심사 상태",
    "IC": "강사 지원 접수 경로",
    "IQ": "문의 분류",
    "IS": "강사 승인 상태",
    "JR": "작업 결과",
    "MS": "회원 상태",
    "MT": "회원 유형",
    "OR": "운영 기준 검토 상태",
    "PM": "결제수단",
    "PS": "결제 상태",
    "PT": "게시물 유형",
    "RA": "거주 지역",
    "RM": "거주 확인 방법",
    "RS": "환불 상태",
    "RV": "거주 확인 상태",
    "SA": "집계자료 검증 상태",
    "SC": "일정 변경 유형",
    "SG": "문자 대상 범위",
    "SK": "관리 범위 유형",
    "SM": "문자 유형",
    "SS": "문자 수신 상태",
}
# 사용 여부를 바꿀 수 있는 그룹. 기관이 정하는 목록만이고 업무 규칙이 쓰는 그룹은 항상 사용이다(사용자 확정 2026-11-16)
USE_EDITABLE = frozenset({"IQ", "CC"})
# 코드를 쓰는 업무 건수를 셀 수 있는 그룹의 (표, 컬럼). 없는 그룹은 건수를 모른다(null)
REFERENCES = {
    "IQ": (TB_PST, "INQRY_CLSF_CD"),
    "PT": (TB_PST, "PST_TYPE_CD"),
    "BT": (TB_BBS, "BBS_TYPE_CD"),
    "ES": (TB_ATNLC_APLY, "APLY_STTS_CD"),
    "PS": (TB_STLM, "STLM_STTS_CD"),
    "PM": (TB_STLM, "STLM_MNS_CD"),
    "RS": (TB_RFND, "RFND_STTS_CD"),
    "MS": (TB_MBR, "MBR_STTS_CD"),
    "RA": (TB_MBR, "HAB_RGN_CD"),
    "RV": (TB_MBR, "HAB_IDNTY_STTS_CD"),
    "CS": (TB_CORS, "CORS_STTS_CD"),
    "IS": (TB_INSTR, "INSTR_STTS_CD"),
    "IA": (TB_INSTR_APLY, "SRNG_STTS_CD"),
    "IC": (TB_INSTR_APLY, "RCPT_CHNL_CD"),
    "DS": (TB_RDCT_BFHD_SRNG, "SRNG_STTS_CD"),
    "FS": (TB_FILE, "FILE_STTS_CD"),
    "FP": (TB_FILE, "FILE_USE_CD"),
    "SS": (TB_SMS_TRGT, "TRGT_STTS_CD"),
    "SM": (TB_SMS_DMND, "DMND_TYPE_CD"),
    "SG": (TB_SMS_DMND, "TRGT_TYPE_CD"),
}


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


# --- 운영 설정 ----------------------------------------------------------------------------------


def _rule_status(row: Any) -> OperRuleStatus:
    return (
        RULE_STATUS.get(str(row.RVW_STTS_CD).strip(), OperRuleStatus.REVIEW)
        if row.RVW_STTS_CD
        else OperRuleStatus.REVIEW
    )


def _summary_text(body: Any) -> str:
    first = str(body or "").strip().splitlines()[0] if str(body or "").strip() else ""
    return first if len(first) <= SUMMARY_CHARS else first[:SUMMARY_CHARS] + "…"


def _summary(row: Any) -> SettingSummary:
    return SettingSummary(
        setting_id=str(int(row.SITE_CONTS_SN)),
        name=str(row.CONTS_TTL),
        value=_summary_text(row.CONTS_CN),
        status=_rule_status(row),
        updated_on=kst_today(row.MDFCN_DT or row.REG_DT),
    )


def _rules(bundle_sn: int) -> Select[Any]:
    return select(TB_SITE_CONTS).where(
        TB_SITE_CONTS.c.OPER_BNDL_SN == bundle_sn, TB_SITE_CONTS.c.CONTS_TYPE_CD == OPER_RULE
    )


def list_settings(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    status: OperRuleStatus | None,
    q: str | None,
    page: int,
    size: int,
) -> SettingPage:
    """운영 기준 항목마다 가장 최근 버전만 나온다. 확정은 실제 기능에 적용되었다는 뜻이 아니다."""
    _whole(db, admin, now)
    newer = TB_SITE_CONTS.alias("newer")
    query = _rules(admin.bundle_sn).where(
        ~exists().where(
            newer.c.OPER_BNDL_SN == TB_SITE_CONTS.c.OPER_BNDL_SN,
            newer.c.CONTS_TYPE_CD == OPER_RULE,
            newer.c.CONTS_ID == TB_SITE_CONTS.c.CONTS_ID,
            newer.c.SITE_CONTS_SN > TB_SITE_CONTS.c.SITE_CONTS_SN,
        )
    )
    if status is OperRuleStatus.REVIEW:
        query = query.where(
            (TB_SITE_CONTS.c.RVW_STTS_CD == STATUS_CODE[status]) | TB_SITE_CONTS.c.RVW_STTS_CD.is_(None)
        )
    elif status is not None:
        query = query.where(TB_SITE_CONTS.c.RVW_STTS_CD == STATUS_CODE[status])
    if q and q.strip():
        query = query.where(TB_SITE_CONTS.c.CONTS_TTL.contains(q.strip(), autoescape=True))
    query = query.order_by(TB_SITE_CONTS.c.SORT_SEQ, TB_SITE_CONTS.c.SITE_CONTS_SN)
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return SettingPage(
        items=[_summary(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def _whole(db: Session, admin: Admin, now: datetime) -> None:
    """운영 기준은 묶음 공통이라 묶음 전체 범위의 담당자만 본다(PRD Q21 후보 AU.SITE_W)."""
    if not permit(db, admin, AU.SITE_W, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)


def get_setting(db: Session, admin: Admin, *, now: datetime, setting_id: str) -> SettingDetail:
    _whole(db, admin, now)
    row = db.execute(_rules(admin.bundle_sn).where(TB_SITE_CONTS.c.SITE_CONTS_SN == int(setting_id))).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    version = int(
        db.execute(
            select(func.count()).where(
                TB_SITE_CONTS.c.OPER_BNDL_SN == admin.bundle_sn,
                TB_SITE_CONTS.c.CONTS_TYPE_CD == OPER_RULE,
                TB_SITE_CONTS.c.CONTS_ID == row.CONTS_ID,
                TB_SITE_CONTS.c.SITE_CONTS_SN <= row.SITE_CONTS_SN,
            )
        ).scalar_one()
    )
    return SettingDetail(
        **_summary(row).model_dump(), body="" if row.CONTS_CN is None else str(row.CONTS_CN), version=version
    )


# --- 공통 코드 ----------------------------------------------------------------------------------


def _grant(db: Session, admin: Admin, now: datetime) -> None:
    """공통 코드는 사이트 전체에 걸쳐 묶음 전체 범위의 AU.GRANT_W만 본다(개정 요청 R20 가정)."""
    if not permit(db, admin, AU.GRANT_W, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)


def _group(db: Session, group_id: str) -> CodeGroup:
    exists_ = db.execute(
        select(TB_COM_CD.c.COM_CD).where(TB_COM_CD.c.CD_GROUP_ID == group_id).limit(1)
    ).first()
    if exists_ is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return CodeGroup(id=group_id, name=GROUP_NAMES.get(group_id, group_id))


def list_groups(db: Session, admin: Admin, *, now: datetime) -> CodeGroupList:
    _grant(db, admin, now)
    ids = [
        str(r[0]).strip()
        for r in db.execute(select(TB_COM_CD.c.CD_GROUP_ID).distinct().order_by(TB_COM_CD.c.CD_GROUP_ID))
    ]
    return CodeGroupList(items=[CodeGroup(id=g, name=GROUP_NAMES.get(g, g)) for g in ids])


def _ref_counts(db: Session, group_id: str) -> dict[str, int] | None:
    found = REFERENCES.get(group_id)
    if found is None:
        return None
    table, column = found
    rows = db.execute(select(table.c[column], func.count()).group_by(table.c[column]))
    return {str(code).strip(): int(count) for code, count in rows if code is not None}


def _code_list(db: Session, group: CodeGroup, *, q: str | None = None, use: bool | None = None) -> CodeList:
    query = select(TB_COM_CD).where(TB_COM_CD.c.CD_GROUP_ID == group.id)
    if use is not None:
        query = query.where(TB_COM_CD.c.USE_YN == ("Y" if use else "N"))
    if q and q.strip():
        needle = q.strip()
        query = query.where(
            TB_COM_CD.c.COM_CD.contains(needle, autoescape=True)
            | TB_COM_CD.c.CD_NM.contains(needle, autoescape=True)
        )
    counts = _ref_counts(db, group.id)
    rows = db.execute(query.order_by(TB_COM_CD.c.SORT_SEQ, TB_COM_CD.c.COM_CD)).all()
    return CodeList(
        group=group,
        items=[
            CodeRow(
                code=str(r.COM_CD).strip(),
                name=str(r.CD_NM),
                sort_seq=int(r.SORT_SEQ),
                use=r.USE_YN == "Y",
                ref_count=None if counts is None else counts.get(str(r.COM_CD).strip(), 0),
            )
            for r in rows
        ],
    )


def list_codes(
    db: Session, admin: Admin, *, now: datetime, group: str, q: str | None, use: bool | None
) -> CodeList:
    _grant(db, admin, now)
    return _code_list(db, _group(db, group), q=q, use=use)


def update_codes(db: Session, admin: Admin, *, now: datetime, request_id: str, body: CodeUpdate) -> CodeList:
    """한 그룹의 표시명·순서·사용 여부만 한 번에 고친다. 하나라도 거절되면 아무것도 저장하지 않는다."""
    _grant(db, admin, now)
    group = _group(db, body.group_id)
    codes = [item.code for item in body.items]
    if len(set(codes)) != len(codes):
        raise _fail("items", "같은 코드가 두 번 들어 있습니다.")
    rows = {
        str(r.COM_CD).strip(): r
        for r in db.execute(
            select(TB_COM_CD)
            .where(TB_COM_CD.c.CD_GROUP_ID == group.id, TB_COM_CD.c.COM_CD.in_(codes))
            .with_for_update()
        )
    }
    if set(rows) != set(codes):
        raise ApiError(ErrorCode.NOT_FOUND)
    changes: list[dict[str, Any]] = []
    for item in body.items:
        current = rows[item.code]
        name = item.name.strip()
        if not name:
            raise _fail("items", f"{item.code}의 표시명을 입력해 주세요.")
        if item.use != (current.USE_YN == "Y") and group.id not in USE_EDITABLE:
            raise _fail("items", f"{group.name}은(는) 업무 규칙이 쓰는 코드라 사용 여부를 바꿀 수 없습니다.")
        if (
            name != current.CD_NM
            or item.sort_seq != int(current.SORT_SEQ)
            or item.use != (current.USE_YN == "Y")
        ):
            changes.append(
                {
                    "code": item.code,
                    "name": [str(current.CD_NM), name],
                    "sort": [int(current.SORT_SEQ), item.sort_seq],
                    "use": [current.USE_YN == "Y", item.use],
                }
            )
            db.execute(
                update(TB_COM_CD)
                .where(TB_COM_CD.c.COM_CD == current.COM_CD)
                .values(CD_NM=name, SORT_SEQ=item.sort_seq, USE_YN="Y" if item.use else "N", MDFCN_DT=now)
            )
    if changes:
        record_job(
            db,
            actor="AK.ADMIN",
            job="CODE_UPDATE",
            table="TB_COM_CD",
            key=group.id,
            request_id=request_id,
            now=now,
            bundle_sn=admin.bundle_sn,
            admin_sn=admin.admin_sn,
            change=json.dumps(changes, ensure_ascii=False)[:3900],
        )
    return _code_list(db, group)
