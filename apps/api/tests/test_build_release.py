# 배포 산출물 묶기(deploy/build-release.sh)를 임시 git 저장소로 확인하는 시험. 웹 빌드는 건너뛴다(ADR-103)
import subprocess
import tarfile
from pathlib import Path

import pytest

from tests.test_deploy_drafts import BASH, DEPLOY, needs_bash, posix

pytestmark = needs_bash


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """api·deploy·웹 앱이 있는 작은 저장소. dist·.env·node_modules는 git이 무시한다(실제 저장소와 같다)."""
    root = tmp_path / "repo"
    (root / "apps/api/app").mkdir(parents=True)
    (root / "apps/web-user").mkdir(parents=True)
    (root / "apps/web-admin").mkdir(parents=True)
    (root / "deploy").mkdir()
    (root / "apps/api/pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (root / "apps/api/uv.lock").write_text("lock\n", encoding="utf-8")
    (root / "apps/api/app/main.py").write_text("app = 1\n", encoding="utf-8")
    (root / "deploy/deploy.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (root / "apps/web-user/package.json").write_text("{}\n", encoding="utf-8")
    (root / ".gitignore").write_text("dist/\n.env\nnode_modules/\nrelease-out/\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    for app in ("web-user", "web-admin"):
        (root / f"apps/{app}/dist").mkdir()
        (root / f"apps/{app}/dist/index.html").write_text(f"<html>{app}</html>", encoding="utf-8")
    (root / "apps/api/.env").write_text("JORI_SECRET_KEY=비밀\n", encoding="utf-8")
    (root / "apps/web-user/node_modules").mkdir()
    (root / "apps/web-user/node_modules/lib.js").write_text("x", encoding="utf-8")
    return root


def build(repo: Path, out: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    env = {"PATH": "/usr/bin:/bin:/mingw64/bin", "JORI_REPO_DIR": posix(repo), "JORI_RELEASE_OUT": posix(out)}
    return subprocess.run(
        [BASH, posix(DEPLOY / "build-release.sh"), *flags],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
        check=False,
    )


def test_스크립트는_문법이_맞고_초안_표시와_dry_run을_받는다() -> None:
    path = DEPLOY / "build-release.sh"
    assert subprocess.run([str(BASH), "-n", posix(path)], capture_output=True, check=False).returncode == 0
    text = path.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text and "초안(미검증)" in text and "--dry-run" in text
    assert b"\r" not in path.read_bytes()


def test_커밋하지_않은_변경이_있으면_묶지_않는다(repo: Path, tmp_path: Path) -> None:
    (repo / "apps/api/app/main.py").write_text("app = 2\n", encoding="utf-8")
    result = build(repo, tmp_path / "out", "--skip-build")
    assert result.returncode == 2 and "커밋하지 않은 변경" in result.stderr
    assert not (tmp_path / "out").exists()


def test_dry_run은_의존성_설치_빌드_묶기_해시_순서를_보이고_아무것도_만들지_않는다(
    repo: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    result = build(repo, out, "--dry-run")
    assert result.returncode == 0, result.stderr
    text = result.stdout
    order = [
        text.index(word)
        for word in (
            "install --frozen-lockfile",
            "@jori/api-client build",
            "@jori/web-user build",
            "@jori/web-admin build",
            "git -C",
            "tar -czf",
            "sha256sum",
        )
    ]
    assert order == sorted(order)
    assert not out.exists()


def test_묶으면_추적하는_파일과_웹_dist만_담고_비밀값과_node_modules는_담지_않는다(
    repo: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    result = build(repo, out, "--skip-build")
    assert result.returncode == 0, result.stderr
    commit = git(repo, "rev-parse", "HEAD")
    archive = out / f"jori-{commit[:12]}.tar.gz"
    assert (
        archive.exists()
        and (out / f"{archive.name}.sha256").read_text(encoding="utf-8").split()[1].lstrip("*")
        == archive.name  # 윈도의 bash는 이름 앞에 *(이진 표시)를 붙인다
    )
    with tarfile.open(archive) as tar:
        names = {name.removeprefix("./") for name in tar.getnames()}
    must = {
        "apps/api/pyproject.toml",
        "apps/api/uv.lock",
        "apps/api/app/main.py",
        "deploy/deploy.sh",
        "apps/web-user/dist/index.html",
        "apps/web-admin/dist/index.html",
    }
    assert must <= names, must - names
    assert not any(".env" in n or "node_modules" in n for n in names)
    assert not (out / f"stage-{commit[:12]}").exists()  # 임시 폴더는 치운다


def test_웹_dist가_없으면_묶지_않고_알린다(repo: Path, tmp_path: Path) -> None:
    for app in ("web-user", "web-admin"):
        (repo / f"apps/{app}/dist/index.html").unlink()
    result = build(repo, tmp_path / "out", "--skip-build")
    assert result.returncode == 2 and "dist가 없습니다" in result.stderr
