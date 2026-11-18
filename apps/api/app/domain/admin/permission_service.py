# 로그인한 관리자의 현재 유효 배정에서 권한 코드·역할 이름·메뉴를 만드는 서비스(FN-056). 메뉴는 노출용이고 모든 요청은 서버가 다시 판정한다
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.admin_access import STRUCTURE_AUTHORITIES, Admin
from app.db.tables import TB_MNGR_ROLE, TB_MNGR_SCP, TB_OPER_BNDL, TB_ROLE_AUTHRT
from app.domain.admin.schemas import AdminPermissions, MenuGroup, MenuItem
from app.domain.admin.types import AdminAuthority as A

# (묶음 키, 묶음 제목, [(항목 키, 이름, 경로, 하나라도 있으면 보이는 권한)]). 화면설계서 2.2·3.2와 TDD 9.3 경로를 따른다
_MENU: tuple[tuple[str, str, tuple[tuple[str, str, str, tuple[A, ...]], ...]], ...] = (
    (
        "status",
        "운영 현황",
        (
            ("dashboard", "대시보드", "/dashboard", (A.STAT_R,)),
            ("stats", "수요·연령·정산 통계", "/stats", (A.STAT_R,)),
            ("stats-sources", "연령·성별 집계자료", "/stats-sources", (A.CONF_W, A.GRANT_W)),
        ),
    ),
    (
        "edu",
        "교육 운영",
        (
            ("courses", "강좌 관리", "/edu/courses", (A.CORS_R, A.CORS_W)),
            ("cycles", "교육기수", "/edu/cycles", (A.CONF_W,)),
            ("schedules", "일정·휴보강", "/edu/schedules", (A.CORS_W,)),
            ("instructors", "강사 심사", "/edu/instructors", (A.INSTR_W,)),
            ("facilities", "센터·강의실", "/edu/facilities", (A.FCLT_W,)),
            ("attendance", "출석 현황", "/edu/attendance", (A.ATND_R,)),
        ),
    ),
    (
        "pay",
        "수강·정산",
        (
            ("applications", "수강신청", "/pay/applications", (A.APLY_R,)),
            ("waitlist", "대기·자리 배정", "/pay/waitlist", (A.APLY_R,)),
            ("transactions", "결제·거래 대조", "/pay/transactions", (A.STLM_R, A.STLM_W)),
            ("refunds", "환불 검토", "/pay/refunds", (A.RFND_A, A.RFND_X)),
            ("reductions", "감면 검토", "/pay/reductions", (A.APLY_R,)),
            ("reduction-history", "감면 처리 이력", "/pay/reduction-history", (A.APLY_R,)),
        ),
    ),
    (
        "member",
        "회원·콘텐츠",
        (
            ("members", "회원 관리", "/mbr/members", (A.MBR_R,)),
            ("posts", "게시물", "/mbr/posts", (A.POST_W,)),
            ("boards", "게시판 설정", "/mbr/boards", (A.BBS_W,)),
            ("inquiries", "문의·답변", "/mbr/inquiries", (A.POST_W,)),
            ("contents", "홈·센터 콘텐츠", "/mbr/contents", (A.SITE_W,)),
            ("terms", "약관·동의문", "/mbr/terms", (A.SITE_W,)),
            ("files", "첨부파일", "/mbr/files", (A.POST_W, A.SITE_W)),
            ("name-changes", "이름 변경 검토", "/mbr/name-changes", (A.GRANT_W,)),
        ),
    ),
    (
        "system",
        "시스템",
        (
            ("sms", "알림 이력", "/sys/sms", (A.SMS_SEND,)),
            ("roles", "권한 배정", "/sys/roles", (A.GRANT_W,)),
            ("settings", "운영 설정", "/sys/settings", (A.SITE_W,)),
            ("codes", "공통 코드", "/sys/codes", (A.GRANT_W,)),
            ("classes", "강좌분류", "/sys/classes", (A.CORS_R,)),
            ("retention", "보존·파기 검토", "/sys/retention", (A.LOG_R,)),
        ),
    ),
)


# 회원·집계 자료를 바꾸는 화면. 시스템 배정(구조 권한)만 가진 담당자에게는 보이지 않는다(R20)
_BUSINESS_KEYS = frozenset({"stats-sources", "name-changes"})


def _menu_for(held: frozenset[A], business: frozenset[A]) -> list[MenuGroup]:
    groups: list[MenuGroup] = []
    for key, title, items in _MENU:
        shown = [
            MenuItem(key=k, label=label, path=path)
            for k, label, path, need in items
            if (business if k in _BUSINESS_KEYS else held) & set(need)
        ]
        if shown:
            groups.append(MenuGroup(key=key, title=title, items=shown))
    return groups


def get_permissions(db: Session, admin: Admin, *, now: datetime) -> AdminPermissions:
    """배정 행마다 사용 중·유효기간·이 묶음을 함께 보고, 맞는 행의 역할 권한만 모은다. SK.SYSTEM 배정은 구조 권한만 갖는다."""
    rows = db.execute(
        select(TB_MNGR_SCP.c.SCP_TYPE_CD, TB_MNGR_ROLE.c.ROLE_NM, TB_ROLE_AUTHRT.c.AUTHRT_CD)
        .join(TB_MNGR_ROLE, TB_MNGR_ROLE.c.ROLE_SN == TB_MNGR_SCP.c.ROLE_SN)
        .outerjoin(TB_ROLE_AUTHRT, TB_ROLE_AUTHRT.c.ROLE_SN == TB_MNGR_SCP.c.ROLE_SN)
        .where(
            TB_MNGR_SCP.c.MNGR_SN == admin.admin_sn,
            TB_MNGR_SCP.c.USE_YN == "Y",
            TB_MNGR_ROLE.c.USE_YN == "Y",
            TB_MNGR_SCP.c.VLD_BGNG_DT <= now,
            or_(TB_MNGR_SCP.c.VLD_END_DT.is_(None), TB_MNGR_SCP.c.VLD_END_DT > now),
            or_(TB_MNGR_SCP.c.OPER_BNDL_SN.is_(None), TB_MNGR_SCP.c.OPER_BNDL_SN == admin.bundle_sn),
        )
        .order_by(TB_MNGR_SCP.c.MNGR_SCP_SN)
    ).all()
    known = {a.value: a for a in A}
    held: set[A] = set()
    business: set[A] = set()
    roles: list[str] = []
    for row in rows:
        name = str(row.ROLE_NM)
        if name not in roles:
            roles.append(name)
        code = known.get(str(row.AUTHRT_CD).strip()) if row.AUTHRT_CD is not None else None
        if code is None:
            continue  # 기능을 켜지 않는 코드(AU.MBR_W 등)는 내보내지 않는다
        if str(row.SCP_TYPE_CD).strip() == "SK.SYSTEM" and code not in STRUCTURE_AUTHORITIES:
            continue
        held.add(code)
        if str(row.SCP_TYPE_CD).strip() == "SK.GROUP":  # 묶음 전체 범위만 이 화면들을 쓴다
            business.add(code)
    label = db.execute(
        select(TB_OPER_BNDL.c.OPER_BNDL_NM).where(TB_OPER_BNDL.c.OPER_BNDL_SN == admin.bundle_sn)
    ).scalar()
    return AdminPermissions(
        role_names=roles,
        scope_label=str(label) if label is not None else "",
        authorities=[a for a in A if a in held],
        menu=_menu_for(frozenset(held), frozenset(business)),
    )
