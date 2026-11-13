# 관리자 출석 현황 조회(AU.ATND_R). 조회 전용이고 수정·삭제·CSV는 없으며 연락처·생년·결제정보는 담지 않는다(FN-064, DV112, ADR-062)
from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, permit
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import utc
from app.db.tables import TB_ATNLC_APLY, TB_CORS, TB_CORS_ATND, TB_CORS_ATND_DTL, TB_INSTR, TB_MBR
from app.domain.admin.attendance_schemas import (
    AttendanceDetail,
    AttendancePage,
    AttendanceRow,
    AttendanceSummary,
)
from app.domain.admin.education_types import AttendanceInputStatus, AttendanceMark
from app.domain.admin.refund_service import mask_name
from app.domain.admin.types import AdminAuthority as AU

MARK = {
    "AR.PRESENT": AttendanceMark.PRESENT,
    "AR.ABSENT": AttendanceMark.ABSENT,
    "AR.UNCHECKED": AttendanceMark.UNCHECKED,  # 미체크를 결석으로 바꾸지 않는다
}
MEMBER_STATUS = {"MS.ACTIVE": "정상", "MS.LOCKED": "잠금", "MS.WITHDRAW": "탈퇴"}  # 표시 이름은 서버가 정한다


def _base(bundle_sn: int) -> Select[Any]:
    source = (
        TB_CORS_ATND.join(
            TB_CORS,
            (TB_CORS.c.OPER_BNDL_SN == TB_CORS_ATND.c.OPER_BNDL_SN)
            & (TB_CORS.c.CORS_SN == TB_CORS_ATND.c.CORS_SN),
        )
        .outerjoin(
            TB_INSTR,
            (TB_INSTR.c.OPER_BNDL_SN == TB_CORS_ATND.c.OPER_BNDL_SN)
            & (TB_INSTR.c.INSTR_SN == TB_CORS_ATND.c.INSTR_SN),
        )
        .outerjoin(TB_MBR, TB_MBR.c.MBR_SN == TB_INSTR.c.MBR_SN)
    )
    return (
        select(
            TB_CORS_ATND,
            TB_CORS.c.CORS_NM,
            TB_CORS.c.DONG_SN,
            TB_CORS.c.EDU_CYCL_SN,
            TB_MBR.c.MBR_NM.label("INSTR_NM"),
        )
        .select_from(source)
        .where(TB_CORS_ATND.c.OPER_BNDL_SN == bundle_sn, TB_CORS_ATND.c.DEL_YN == "N")
    )


def _summary(row: Any) -> AttendanceSummary:
    return AttendanceSummary(
        attendance_id=str(int(row.ATND_SN)),
        course_id=str(int(row.CORS_SN)),
        course_name=str(row.CORS_NM),
        class_date=date(int(str(row.LCTR_YMD)[:4]), int(str(row.LCTR_YMD)[4:6]), int(str(row.LCTR_YMD)[6:8])),
        session=int(row.LCTR_SEQ),
        instructor_name="" if row.INSTR_NM is None else str(row.INSTR_NM),
        present=int(row.ATND_NOPE),
        absent=int(row.ABSNC_NOPE),
        unchecked=int(row.UNCHCK_NOPE),
        input_status=AttendanceInputStatus.DONE if row.CMPTN_YN == "Y" else AttendanceInputStatus.IN_PROGRESS,
    )


def list_attendance(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    cycle_id: str | None,
    course_id: str | None,
    class_date: date | None,
    input_status: AttendanceInputStatus | None,
    page: int,
    size: int,
) -> AttendancePage:
    """출석부는 수업일이 늦은 것이 먼저다. 범위는 강좌의 운영 동이다."""
    scope = permit(db, admin, AU.ATND_R, now)
    query = _base(admin.bundle_sn)
    if not scope.whole:
        query = query.where(TB_CORS.c.DONG_SN.in_(scope.dongs))
    if cycle_id:
        query = query.where(TB_CORS.c.EDU_CYCL_SN == int(cycle_id))
    if course_id:
        query = query.where(TB_CORS_ATND.c.CORS_SN == int(course_id))
    if class_date is not None:
        query = query.where(TB_CORS_ATND.c.LCTR_YMD == class_date.strftime("%Y%m%d"))
    if input_status is not None:
        query = query.where(
            TB_CORS_ATND.c.CMPTN_YN == ("Y" if input_status is AttendanceInputStatus.DONE else "N")
        )
    query = query.order_by(TB_CORS_ATND.c.LCTR_YMD.desc(), TB_CORS.c.CORS_NM, TB_CORS_ATND.c.ATND_SN.desc())
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return AttendancePage(
        items=[_summary(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def get_attendance(db: Session, admin: Admin, *, now: datetime, attendance_id: str) -> AttendanceDetail:
    """명단은 가린 이름·신청번호·회원 상태·출석 상태만 담는다. 범위 밖이거나 지운 출석부는 같은 404다."""
    scope = permit(db, admin, AU.ATND_R, now)
    row = db.execute(_base(admin.bundle_sn).where(TB_CORS_ATND.c.ATND_SN == int(attendance_id))).first()
    if row is None or not scope.covers(None if row.DONG_SN is None else int(row.DONG_SN)):
        raise ApiError(ErrorCode.NOT_FOUND)
    roster = db.execute(
        select(
            TB_CORS_ATND_DTL.c.ATND_RSLT_CD,
            TB_ATNLC_APLY.c.ATNLC_APLY_SN,
            TB_MBR.c.MBR_NM,
            TB_MBR.c.MBR_STTS_CD,
        )
        .select_from(
            TB_CORS_ATND_DTL.join(
                TB_ATNLC_APLY,
                (TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_CORS_ATND_DTL.c.OPER_BNDL_SN)
                & (TB_ATNLC_APLY.c.ATNLC_APLY_SN == TB_CORS_ATND_DTL.c.ATNLC_APLY_SN),
            ).join(TB_MBR, TB_MBR.c.MBR_SN == TB_ATNLC_APLY.c.MBR_SN)
        )
        .where(TB_CORS_ATND_DTL.c.OPER_BNDL_SN == admin.bundle_sn, TB_CORS_ATND_DTL.c.ATND_SN == row.ATND_SN)
        .order_by(TB_MBR.c.MBR_NM, TB_ATNLC_APLY.c.ATNLC_APLY_SN)
    ).all()
    return AttendanceDetail(
        **_summary(row).model_dump(),
        sheet_no=str(int(row.ATND_SN)),
        roster=[
            AttendanceRow(
                name=mask_name(str(r.MBR_NM)),
                application_no=str(int(r.ATNLC_APLY_SN)),
                member_status=MEMBER_STATUS.get(str(r.MBR_STTS_CD), "확인 필요"),
                mark=MARK[str(r.ATND_RSLT_CD)],
            )
            for r in roster
        ],
    )
