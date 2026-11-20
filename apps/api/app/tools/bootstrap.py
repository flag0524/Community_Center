# 새 배포의 최초 설정. 운영묶음·행정동·최초 관리자를 한 트랜잭션으로 만든다. 관리자가 있으면 거부한다
import argparse
import getpass
import re
import sys
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.passwords import hash_password
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, open_session
from app.db.tables import TB_DONG, TB_MNGR, TB_MNGR_ROLE, TB_MNGR_SCP, TB_OPER_BNDL, TB_ROLE_AUTHRT
from app.domain.admin.types import AdminAuthority

SITE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")  # 소문자 영숫자·하이픈(설계안 4.1)
LOGIN_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{3,19}$")  # 컬럼은 VARCHAR(20)
MIN_PASSWORD = 12
FIRST_ROLE_ID = "bootstrap-admin"
FIRST_ROLE_NAME = "최초 관리자"
JOB = "BOOTSTRAP"


class BootstrapError(Exception):
    """입력이 틀렸거나 이미 설정된 배포라 아무것도 만들지 않았다. 메시지에 비밀번호는 담지 않는다."""


@dataclass(frozen=True)
class SiteSpec:
    site_id: str
    bundle_name: str
    site_name: str
    url: str
    timezone: str = "Asia/Seoul"


@dataclass(frozen=True)
class AdminSpec:
    login_id: str
    name: str
    password: str


@dataclass(frozen=True)
class BootstrapResult:
    bundle_sn: int
    admin_sn: int
    dong_count: int
    bundle_created: bool


def read_dongs(path: Path) -> list[str]:
    """기관이 준 행정동 명단. 한 줄에 하나이고 빈 줄과 #으로 시작하는 줄은 건너뛴다."""
    names = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name = line.strip()
        if name and not name.startswith("#"):
            names.append(name)
    return names


def _check_password(password: str) -> None:
    classes = sum(
        bool(re.search(pattern, password)) for pattern in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]")
    )
    if len(password) < MIN_PASSWORD or classes < 3:
        raise BootstrapError(
            f"비밀번호는 {MIN_PASSWORD}자 이상이고 영문 대소문자·숫자·기호 중 3종류를 써야 합니다."
        )


def validate(site: SiteSpec, admin: AdminSpec, dongs: Sequence[str]) -> None:
    """쓰기 전에 입력을 모두 검사한다. 하나라도 틀리면 아무것도 만들지 않는다."""
    if not SITE_ID_PATTERN.fullmatch(site.site_id):
        raise BootstrapError("사이트 식별자는 소문자 영숫자·하이픈이며 40자 이내여야 합니다.")
    for label, value, limit in (("운영묶음명", site.bundle_name, 100), ("사이트명", site.site_name, 100)):
        if not value.strip() or len(value) > limit:
            raise BootstrapError(f"{label}은 1~{limit}자여야 합니다.")
    if not (site.url.startswith("https://") and len(site.url) <= 2000):
        raise BootstrapError("사이트 주소는 https://로 시작해야 합니다.")
    if not LOGIN_ID_PATTERN.fullmatch(admin.login_id):
        raise BootstrapError("관리자 아이디는 영문으로 시작하는 4~20자(영숫자·.·_·-)여야 합니다.")
    if not admin.name.strip() or len(admin.name) > 100:
        raise BootstrapError("관리자 이름은 1~100자여야 합니다.")
    _check_password(admin.password)
    if not dongs:
        raise BootstrapError("행정동 명단이 비어 있습니다.")
    if len(set(dongs)) != len(dongs):
        raise BootstrapError("행정동 명단에 같은 이름이 둘 이상 있습니다.")
    if any(len(name) > 40 for name in dongs):
        raise BootstrapError("행정동 이름은 40자 이내여야 합니다.")


def _naive(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(tzinfo=None) if now.tzinfo else now


def bootstrap(
    db: Session,
    settings: Settings,
    site: SiteSpec,
    admin: AdminSpec,
    dongs: Sequence[str],
    *,
    now: datetime,
    request_id: str,
) -> BootstrapResult:
    """커밋은 부르는 쪽이 한다. 중간에 예외가 나면 부르는 쪽이 되돌려 반쯤 만든 상태가 남지 않는다."""
    validate(site, admin, dongs)
    stamp = _naive(now)
    if int(db.execute(select(func.count()).select_from(TB_MNGR)).scalar_one()) > 0:
        raise BootstrapError("이미 관리자가 있는 배포입니다. 최초 설정은 한 번만 할 수 있습니다.")

    found = db.execute(
        select(TB_OPER_BNDL.c.OPER_BNDL_SN, TB_OPER_BNDL.c.USE_YN).where(
            TB_OPER_BNDL.c.SITE_ID == site.site_id
        )
    ).first()
    if found is not None and found.USE_YN != "Y":
        raise BootstrapError("같은 식별자의 사이트가 중지 상태입니다. 먼저 사용 중으로 바꾸세요.")
    created = found is None
    if found is None:
        bundle_sn = int(
            db.execute(
                insert(TB_OPER_BNDL)
                .values(
                    OPER_BNDL_NM=site.bundle_name.strip(),
                    SITE_NM=site.site_name.strip(),
                    SITE_ID=site.site_id,
                    URL_ADDR=site.url,
                    TMZN_NM=site.timezone,
                    REG_DT=stamp,
                )
                .returning(TB_OPER_BNDL.c.OPER_BNDL_SN)
            ).scalar_one()
        )
    else:
        bundle_sn = int(found.OPER_BNDL_SN)

    existing = set(db.execute(select(TB_DONG.c.DONG_NM).where(TB_DONG.c.OPER_BNDL_SN == bundle_sn)).scalars())
    added = [name for name in dongs if name not in existing]
    for order, name in enumerate(added, start=1 + len(existing)):
        db.execute(insert(TB_DONG).values(OPER_BNDL_SN=bundle_sn, DONG_NM=name, SORT_SEQ=order, REG_DT=stamp))

    admin_sn = int(
        db.execute(
            insert(TB_MNGR)
            .values(
                LGN_ID=admin.login_id,
                PSWD_HASH_VL=hash_password(admin.password, settings.pbkdf2_iterations),
                MNGR_NM=admin.name.strip(),
                REG_DT=stamp,
            )
            .returning(TB_MNGR.c.MNGR_SN)
        ).scalar_one()
    )

    role_sn = db.execute(
        select(TB_MNGR_ROLE.c.ROLE_SN).where(TB_MNGR_ROLE.c.ROLE_ID == FIRST_ROLE_ID)
    ).scalar()
    if role_sn is None:
        role_sn = db.execute(
            insert(TB_MNGR_ROLE)
            .values(ROLE_ID=FIRST_ROLE_ID, ROLE_NM=FIRST_ROLE_NAME, REG_DT=stamp)
            .returning(TB_MNGR_ROLE.c.ROLE_SN)
        ).scalar_one()
        for authority in AdminAuthority:
            db.execute(
                insert(TB_ROLE_AUTHRT).values(ROLE_SN=role_sn, AUTHRT_CD=authority.value, REG_DT=stamp)
            )
    # 묶음 배정(SK.GROUP)은 모든 권한을 묶음 전체에 미친다. 부여자는 자기 자신이다(처음 한 번뿐)
    db.execute(
        insert(TB_MNGR_SCP).values(
            MNGR_SN=admin_sn,
            ROLE_SN=role_sn,
            SCP_TYPE_CD="SK.GROUP",
            OPER_BNDL_SN=bundle_sn,
            VLD_BGNG_DT=stamp,
            GRNT_MNGR_SN=admin_sn,
            REG_DT=stamp,
        )
    )

    record_job(
        db,
        actor="AK.SYSTEM",
        job=JOB,
        table="TB_MNGR",
        key=admin_sn,
        request_id=request_id,
        now=stamp,
        bundle_sn=bundle_sn,
        change=f"사이트 {site.site_id} {'생성' if created else '재사용'}, 행정동 {len(added)}건, 최초 관리자",
    )
    return BootstrapResult(bundle_sn, admin_sn, len(added), created)


def _prompt_password(read: Callable[[str], str]) -> str:
    first, again = read("관리자 비밀번호: "), read("한 번 더: ")
    if first != again:
        raise BootstrapError("비밀번호가 서로 다릅니다.")
    return first


def _run(
    settings: Settings, site: SiteSpec, admin: AdminSpec, dongs: Sequence[str]
) -> BootstrapResult:  # pragma: no cover - 실제 DB 연결
    engine = create_db_engine(settings)
    with open_session(engine) as db:
        try:
            result = bootstrap(
                db, settings, site, admin, dongs, now=datetime.now(UTC), request_id=uuid.uuid4().hex
            )
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return result


def main(argv: list[str], *, read_secret: Callable[[str], str] = getpass.getpass) -> int:
    parser = argparse.ArgumentParser(description="새 배포의 운영묶음·행정동·최초 관리자를 만든다(한 번만)")
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--bundle-name", required=True)
    parser.add_argument("--site-name", required=True)
    parser.add_argument("--url", required=True, help="주민용 주소(https://...)")
    parser.add_argument(
        "--dongs-file", required=True, type=Path, help="한 줄에 하나인 행정동 명단(기관 자료)"
    )
    parser.add_argument("--admin-id", required=True)
    parser.add_argument("--admin-name", required=True)
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="비밀번호를 표준입력 한 줄로 받는다(자동화용). 기본은 프롬프트",
    )
    args = parser.parse_args(argv[1:])
    try:
        password = (
            sys.stdin.readline().rstrip("\r\n") if args.password_stdin else _prompt_password(read_secret)
        )
        site = SiteSpec(args.site_id, args.bundle_name, args.site_name, args.url)
        admin = AdminSpec(args.admin_id, args.admin_name, password)
        dongs = read_dongs(args.dongs_file)
        validate(site, admin, dongs)
        result = _run(get_settings(), site, admin, dongs)
    except (BootstrapError, OSError) as error:
        print(f"만들지 않았습니다: {error}", file=sys.stderr)
        return 3
    print(
        f"완료: 사이트 {'생성' if result.bundle_created else '재사용'}, 행정동 {result.dong_count}건, "
        f"최초 관리자 {args.admin_id}. 비밀번호는 기록하지 않았습니다."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
