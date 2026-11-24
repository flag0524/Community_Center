# 개발용 주민 계정을 문자 인증 없이 만드는 도구. 운영 환경에서는 거절한다(ADR-116)
import argparse
import getpass
import re
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.member_phone import sealed_columns
from app.auth.passwords import hash_password
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, open_session
from app.db.tables import TB_MBR, TB_OPER_BNDL
from app.domain.member.schemas import EMAIL_PATTERN, PHONE_PATTERN

LOGIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{3,19}$")  # 컬럼은 VARCHAR(20), 설계안은 소문자 정규화
MIN_PASSWORD = 10  # 가입 요청(JoinRequest)과 같다
MAX_PASSWORD = 64
JOB = "DEV_MEMBER"


class DevMemberError(Exception):
    """입력이 틀렸거나 만들 수 없는 환경이라 아무것도 만들지 않았다. 메시지에 비밀번호·번호는 담지 않는다."""


@dataclass(frozen=True)
class MemberSpec:
    login_id: str
    name: str
    password: str
    phone: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class Created:
    member_sn: int
    login_id: str


def _refuse_production(settings: Settings) -> None:
    if settings.environment == "production":
        raise DevMemberError("운영 환경에서는 쓸 수 없는 개발용 도구입니다.")


def validate(spec: MemberSpec) -> None:
    """쓰기 전에 입력을 모두 검사한다. 하나라도 틀리면 아무것도 만들지 않는다."""
    if not LOGIN_ID_PATTERN.fullmatch(spec.login_id):
        raise DevMemberError("아이디는 소문자 영문으로 시작하는 4~20자(소문자·숫자·.·_·-)여야 합니다.")
    if not spec.name.strip() or len(spec.name) > 100:
        raise DevMemberError("이름은 1~100자여야 합니다.")
    if not MIN_PASSWORD <= len(spec.password) <= MAX_PASSWORD:
        raise DevMemberError(f"비밀번호는 {MIN_PASSWORD}~{MAX_PASSWORD}자여야 합니다.")
    if spec.phone is not None and not re.fullmatch(PHONE_PATTERN, spec.phone):
        raise DevMemberError("휴대전화번호는 01로 시작하는 숫자 10~11자리여야 합니다.")
    if spec.email is not None and (len(spec.email) > 254 or not re.fullmatch(EMAIL_PATTERN, spec.email)):
        raise DevMemberError("이메일 형식이 올바르지 않습니다.")


def create_member(
    db: Session, settings: Settings, spec: MemberSpec, *, now: datetime, request_id: str
) -> Created:
    """커밋은 부르는 쪽이 한다. 가입(join_member)이 넣는 컬럼만 채우고 나머지는 DB 기본값을 쓴다."""
    _refuse_production(settings)
    validate(spec)
    bundle_sn = db.execute(
        select(TB_OPER_BNDL.c.OPER_BNDL_SN).where(
            TB_OPER_BNDL.c.SITE_ID == settings.site_id, TB_OPER_BNDL.c.USE_YN == "Y"
        )
    ).scalar_one_or_none()
    if bundle_sn is None:
        raise DevMemberError("이 사이트의 운영묶음이 없습니다. 먼저 최초 설정(bootstrap)을 하세요.")
    taken = db.execute(
        select(TB_MBR.c.MBR_SN).where(TB_MBR.c.OPER_BNDL_SN == bundle_sn, TB_MBR.c.LGN_ID == spec.login_id)
    ).first()
    if taken is not None:
        raise DevMemberError("이미 있는 아이디입니다.")
    stamp = now.astimezone(UTC).replace(tzinfo=None) if now.tzinfo else now
    member_sn = int(
        db.execute(
            insert(TB_MBR)
            .values(
                OPER_BNDL_SN=int(bundle_sn),
                LGN_ID=spec.login_id,
                PSWD_HASH_VL=hash_password(spec.password, settings.pbkdf2_iterations),
                MBR_NM=spec.name.strip(),
                **sealed_columns(settings.secret_key, spec.phone),
                EML_ADDR=spec.email,
                MBR_JOIN_DT=stamp,
            )
            .returning(TB_MBR.c.MBR_SN)
        ).scalar_one()
    )
    record_job(
        db,
        actor="AK.SYSTEM",
        job=JOB,
        table="TB_MBR",
        key=member_sn,
        request_id=request_id,
        now=stamp,
        bundle_sn=int(bundle_sn),
        change="개발용 회원 생성(문자 인증·약관 동의 없음)",
    )
    return Created(member_sn, spec.login_id)


def _prompt_password(read: Callable[[str], str]) -> str:
    first, again = read("주민 비밀번호: "), read("한 번 더: ")
    if first != again:
        raise DevMemberError("비밀번호가 서로 다릅니다.")
    return first


def _run(settings: Settings, spec: MemberSpec) -> Created:  # pragma: no cover - 실제 DB 연결
    engine = create_db_engine(settings)
    with open_session(engine) as db:
        try:
            result = create_member(db, settings, spec, now=datetime.now(UTC), request_id=uuid.uuid4().hex)
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return result


def main(argv: list[str], *, read_secret: Callable[[str], str] = getpass.getpass) -> int:
    parser = argparse.ArgumentParser(description="개발용 주민 계정을 문자 인증 없이 만든다(운영 환경 거절)")
    parser.add_argument("--login-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--phone", help="휴대전화번호(숫자만). 없으면 번호 없이 만든다")
    parser.add_argument("--email")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="비밀번호를 표준입력 한 줄로 받는다(자동화용). 기본은 프롬프트",
    )
    args = parser.parse_args(argv[1:])
    try:
        settings = get_settings()
        _refuse_production(settings)  # 비밀번호를 묻기 전에 막는다
        password = (
            sys.stdin.readline().rstrip("\r\n") if args.password_stdin else _prompt_password(read_secret)
        )
        spec = MemberSpec(args.login_id, args.name, password, args.phone, args.email)
        validate(spec)
        result = _run(settings, spec)
    except DevMemberError as error:
        print(f"만들지 않았습니다: {error}", file=sys.stderr)
        return 3
    print(f"완료: 주민 계정 {result.login_id}(회원번호 {result.member_sn}). 비밀번호는 기록하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
