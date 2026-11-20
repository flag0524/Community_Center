# 배포 파일(systemd·Nginx·MariaDB·환경 예시)이 앱 설정·워커 감시와 맞는지 파일 내용으로 확인하는 시험
import configparser
import re
import socket
import sys
from pathlib import Path

import pytest

from app.adapters.pg import build_gateway
from app.core.config import ConfigError, load_settings
from app.domain.file.upload import MAX_BYTES
from app.worker.__main__ import WATCHDOG_PING_SECONDS
from app.worker.systemd import notify

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"
DEPLOY_ONLY = {"JORI_API_PORT", "JORI_API_WORKERS"}  # 유닛만 읽는 값
SECRET = "시험용 비밀키 " + "x" * 40


def env_example() -> dict[str, str]:
    values = {}
    for line in (DEPLOY / "env/jori.env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key] = value
    return values


def unit(name: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    parser.read(DEPLOY / "systemd" / name, encoding="utf-8")
    return parser


# --- 환경 예시 -------------------------------------------------------------------------------


def test_환경_예시의_변수는_앱이_읽는_것과_유닛이_읽는_것뿐이다() -> None:
    source = (Path(__file__).resolve().parents[1] / "app/core/config.py").read_text(encoding="utf-8")
    read_by_app = set(re.findall(r'"(JORI_[A-Z_]+)"', source))
    unknown = set(env_example()) - read_by_app - DEPLOY_ONLY
    assert unknown == set(), "앱이 읽지 않는 변수는 오타일 수 있다"


def test_환경_예시는_필수_변수를_모두_갖고_앱_설정으로_읽힌다() -> None:
    values = {**env_example(), "JORI_SECRET_KEY": SECRET}
    settings = load_settings(values)
    assert (settings.environment, settings.site_id, settings.cookie_secure) == ("production", "jori", True)
    assert settings.file_scanner == "clamd"
    assert settings.worker_status_file == "/run/jori/jori/worker-status.json"


def test_예시에는_비밀값이_없고_계약_전_업체_값은_지어내지_않았다() -> None:
    values = env_example()
    assert "CHANGE_ME" in values["JORI_SECRET_KEY"] and "CHANGE_ME" in values["JORI_DATABASE_URL"]
    assert [values[k] for k in ("JORI_PG_PROVIDER", "JORI_PG_MERCHANT_ID", "JORI_SMS_PROVIDER")] == [
        "TBD"
    ] * 3
    assert values["JORI_SMS_SENDER_NUMBER"] == "TBD"


def test_업체를_정하기_전에는_운영_기동이_거절된다() -> None:
    settings = load_settings({**env_example(), "JORI_SECRET_KEY": SECRET})
    with pytest.raises(ConfigError, match="지원하지 않는 결제대행사"):
        build_gateway(settings)  # 운영 기동은 이 확인을 먼저 한다


# --- systemd 유닛 ----------------------------------------------------------------------------


def test_워커_유닛은_알림형이고_watchdog_주기가_워커_신호보다_길다() -> None:
    service = unit("jori-worker@.service")["Service"]
    assert service["Type"] == "notify" and service["NotifyAccess"] == "main"
    watchdog = int(service["WatchdogSec"])
    assert watchdog > WATCHDOG_PING_SECONDS * 2  # 신호 한 번이 늦어도 정지로 보지 않는다
    assert service["Restart"] == "on-failure"
    assert service["ExecStart"].endswith("-m app.worker")


def test_두_유닛은_같은_환경_파일과_계정을_쓰고_상태_폴더가_앱_설정과_맞다() -> None:
    api, worker = unit("jori-api@.service")["Service"], unit("jori-worker@.service")["Service"]
    for key in ("User", "Group", "WorkingDirectory"):
        assert api[key] == worker[key], key
    assert (
        api["EnvironmentFile"] == "/etc/jori/%i.env"
    )  # 워커는 같은 파일에 선택 파일을 더 읽는다(초안 시험이 본다)
    status_dir = "/run/" + worker["RuntimeDirectory"].replace("%i", "jori")
    assert env_example()["JORI_WORKER_STATUS_FILE"].startswith(status_dir + "/")


def test_API_유닛은_예시에_있는_포트와_워커_수를_쓰고_앱_진입점이_있다() -> None:
    service = unit("jori-api@.service")["Service"]
    used = set(re.findall(r"\$\{(JORI_[A-Z_]+)\}", service["ExecStart"]))
    assert used <= set(env_example()) and used == DEPLOY_ONLY
    assert "app.main:app" in service["ExecStart"] and "--proxy-headers" in service["ExecStart"]


def test_유닛은_첨부_저장소만_쓸_수_있게_열어_둔다() -> None:
    for name in ("jori-api@.service", "jori-worker@.service"):
        service = unit(name)["Service"]
        assert service["ProtectSystem"] == "strict" and service["NoNewPrivileges"] == "true"
        assert env_example()["JORI_FILE_ROOT"].startswith(service["ReadWritePaths"].replace("%i", "jori"))


# --- Nginx·MariaDB ---------------------------------------------------------------------------


def test_Nginx는_첨부_한도보다_큰_본문을_받고_관리자_API를_주민_주소로_열지_않는다() -> None:
    conf = (DEPLOY / "nginx/jori.conf.template").read_text(encoding="utf-8")
    sizes = [int(m) for m in re.findall(r"client_max_body_size (\d+)m;", conf)]
    assert sizes and all(size * 1024 * 1024 > MAX_BYTES for size in sizes)
    user_server = conf.split("# 관리자\n")[0]
    assert "location /api/admin/ { return 404; }" in user_server
    code = "\n".join(line for line in conf.splitlines() if not line.lstrip().startswith("#"))
    assert (
        "{{API_PORT}}" in code and "{{DOMAIN}}" in code and "example." not in code
    )  # 예시 도메인을 그대로 두지 않는다


def _limited_locations(server: str) -> list[tuple[str, str]]:
    """server 블록에서 limit_req를 건 정규식 location의 (정규식, 본문)을 모은다."""
    found = []
    for match in re.finditer(r"location ~ (\S+) \{(.*?)\n    \}", server, re.S):
        if "limit_req" in match.group(2):
            found.append((match.group(1), match.group(2)))
    return found


def test_Nginx는_로그인_인증번호_경로에만_IP당_분당_20회_제한을_건다() -> None:
    conf = (DEPLOY / "nginx/jori.conf.template").read_text(encoding="utf-8")
    assert re.search(r"^limit_req_zone \$binary_remote_addr zone=jori_auth:\d+m rate=20r/m;$", conf, re.M)
    assert re.search(r"^limit_req_status 429;$", conf, re.M)
    user_server, admin_server = conf.split("# 관리자\n")
    user, admin = _limited_locations(user_server), _limited_locations(admin_server)
    assert len(user) == 1 and len(admin) == 1
    must_limit = [
        (user[0][0], "/api/v1/auth/login"),
        (user[0][0], "/api/v1/auth/otp"),
        (user[0][0], "/api/v1/auth/otp/verify"),
        (user[0][0], "/api/v1/auth/find-id"),
        (user[0][0], "/api/v1/auth/password-reset"),
        (user[0][0], "/api/v1/join"),
        (admin[0][0], "/api/admin/v1/auth/login"),
    ]
    for pattern, path in must_limit:
        assert re.fullmatch(pattern, path), f"{path}는 제한 대상이어야 한다"
    # 화면을 열 때마다 부르는 경로와 일반 업무 경로는 제한하지 않는다
    for pattern, path in [
        (user[0][0], "/api/v1/auth/session"),
        (user[0][0], "/api/v1/auth/logout"),
        (user[0][0], "/api/v1/courses"),
        (user[0][0], "/api/v1/join/check-id"),
        (admin[0][0], "/api/admin/v1/auth/session"),
        (admin[0][0], "/api/admin/v1/auth/extend"),
    ]:
        assert not re.fullmatch(pattern, path), f"{path}는 제한하지 않는다"
    for _, body in user + admin:
        assert "limit_req zone=jori_auth" in body and "proxy_pass http://jori_api;" in body


def test_MariaDB_설정은_READ_COMMITTED와_행_기반_바이너리_로그다() -> None:
    cnf = (DEPLOY / "mariadb/jori.cnf").read_text(encoding="utf-8")
    assert re.search(r"^transaction_isolation\s*=\s*READ-COMMITTED$", cnf, re.M)
    assert re.search(
        r"^binlog_format\s*=\s*(ROW|MIXED)$", cnf, re.M
    )  # STATEMENT는 READ COMMITTED 쓰기를 거절한다


# --- systemd 알림 ----------------------------------------------------------------------------


def test_알림은_NOTIFY_SOCKET이_있을_때만_보낸다() -> None:
    sent: list[tuple[str, bytes]] = []
    assert notify("WATCHDOG=1", {}, lambda addr, data: sent.append((addr, data))) is False
    assert sent == []
    assert notify("WATCHDOG=1", {"NOTIFY_SOCKET": "/run/systemd/notify"}, lambda a, d: sent.append((a, d)))
    assert sent == [("/run/systemd/notify", b"WATCHDOG=1")]


def test_알림을_못_보내도_예외를_내지_않는다() -> None:
    def broken(address: str, payload: bytes) -> None:
        raise ConnectionRefusedError

    assert notify("READY=1", {"NOTIFY_SOCKET": "/nope"}, broken) is False


def test_실제_유닉스_소켓으로_알림이_도착한다(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("유닉스 소켓은 리눅스에서 확인한다")
    path = str(tmp_path / "notify")
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
        server.bind(path)
        assert notify("READY=1", {"NOTIFY_SOCKET": path}) is True
        assert server.recv(64) == b"READY=1"
