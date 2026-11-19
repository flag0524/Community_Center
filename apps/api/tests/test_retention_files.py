# 삭제한 첨부 원본의 정리(삭제 후 30일, 감면·환불 증빙은 올린 지 5년,
# 판정 근거 증빙 제외)를 확인하는 시험(ADR-096)
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.worker import retention
from tests.test_admin_refunds import call, refund
from tests.test_admin_retention import items
from tests.test_admin_retention_execute import operator, run
from tests.world import START, World

pytestmark = pytest.mark.db

DAY = timedelta(days=1)
YEAR = timedelta(days=365)


@pytest.fixture
def root(world: World, tmp_path: Path) -> Path:
    """저장소 위치를 시험용 임시 폴더로 바꾼다. 관리자 실행도 같은 설정을 쓴다."""
    settings = replace(world.settings, file_root=str(tmp_path))
    world.client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
    return tmp_path


def stored(world: World, root: Path, tag: str, **values: Any) -> dict[str, Any]:
    """저장소에 실제 원본을 쓰고 그 객체키를 가진 파일 행을 만든다."""
    key = f"b{world.bundle}/{tag}"
    (root / key).parent.mkdir(parents=True, exist_ok=True)
    (root / key).write_bytes(b"original")
    defaults: dict[str, Any] = {
        "STRG_KEY": key,
        "FILE_NM": f"{tag}.pdf",
        "FILE_SZ": 8,
        "MIME_TYPE_NM": "application/pdf",
        "FILE_USE_CD": "FP.ATTACH",
        "FILE_STTS_CD": "FS.DELETE",
        "MDFCN_DT": START - 40 * DAY,
    }
    return world.factory.make("TB_FILE", **{**defaults, **values})


def present(root: Path, row: dict[str, Any]) -> bool:
    return (root / str(row["STRG_KEY"])).exists()


def file_rows(world: World) -> set[int]:
    return {int(r) for r in world.db.execute(text("SELECT FILE_SN FROM TB_FILE")).scalars()}


def proof_owner(world: World) -> dict[str, Any]:
    """환불 증빙의 소유자 값(환불 번호). 증빙은 올린 날부터 5년이다."""
    return {"RFND_SN": refund(world, status="RS.DONE")["RFND_SN"]}


def test_삭제_후_30일이_지난_일반_파일과_5년이_지난_증빙만_지우고_나머지는_남긴다(
    world: World, root: Path
) -> None:
    old = stored(world, root, "old", MDFCN_DT=START - 40 * DAY)  # 삭제 40일 전
    recent = stored(world, root, "recent", MDFCN_DT=START - 10 * DAY)  # 삭제 10일 전
    live = stored(
        world, root, "live", FILE_STTS_CD="FS.SAFE", REG_DT=START - 10 * YEAR
    )  # 삭제하지 않은 오래된 파일
    proof_old = stored(world, root, "proofold", REG_DT=START - 6 * YEAR, **proof_owner(world))  # 올린 지 6년
    proof_young = stored(
        world, root, "proofyoung", REG_DT=START - 3 * YEAR, MDFCN_DT=START - 200 * DAY, **proof_owner(world)
    )  # 삭제는 오래전이지만 올린 지 3년이라 5년을 채우지 못했다
    proof_live = stored(
        world, root, "prooflive", FILE_STTS_CD="FS.SAFE", REG_DT=START - 6 * YEAR, **proof_owner(world)
    )
    review = world.factory.make("TB_RDCT_BFHD_SRNG")
    reduction_young = stored(
        world,
        root,
        "reductionyoung",
        REG_DT=START - 3 * YEAR,
        MDFCN_DT=START - 100 * DAY,
        RDCT_BFHD_SRNG_SN=review["RDCT_BFHD_SRNG_SN"],
    )  # 감면 증빙도 올린 지 5년이 안 됐으면 남는다
    other = world.factory.make("TB_OPER_BNDL")
    foreign = world.factory.make(
        "TB_FILE",
        OPER_BNDL_SN=other["OPER_BNDL_SN"],
        STRG_KEY="bother/foreign",
        FILE_NM="f.pdf",
        FILE_SZ=1,
        MIME_TYPE_NM="application/pdf",
        FILE_USE_CD="FP.ATTACH",
        FILE_STTS_CD="FS.DELETE",
        MDFCN_DT=START - 90 * DAY,
    )  # 다른 묶음의 삭제 파일은 세지도 지우지도 않는다
    operator(world)
    listing = items(world)["FILE_ORIGINALS"]
    assert (listing["count"], listing["state"]) == (2, "DUE")
    res = run(world, 8, 2)
    assert res.status_code == 200, res.text
    assert res.json()["executions"][0]["processed"] == 2
    assert file_rows(world) == {
        int(r["FILE_SN"]) for r in (recent, live, proof_young, proof_live, reduction_young, foreign)
    }, (old, proof_old)
    assert not present(root, old) and not present(root, proof_old)
    assert all(present(root, r) for r in (recent, live, proof_young, proof_live, reduction_young))
    assert run(world, 8, 2).status_code == 409  # 더 처리할 대상이 없다


def test_감면_판정의_근거로_연결된_증빙은_오래돼도_지우지_않는다(world: World, root: Path) -> None:
    review = world.factory.make("TB_RDCT_BFHD_SRNG")
    cited = stored(
        world, root, "cited", REG_DT=START - 8 * YEAR, RDCT_BFHD_SRNG_SN=review["RDCT_BFHD_SRNG_SN"]
    )
    world.factory.make("TB_RDCT_HSTRY_FILE", FILE_SN=cited["FILE_SN"])
    operator(world)
    assert items(world)["FILE_ORIGINALS"]["count"] == 0
    assert call(world, "GET", "/retention/8").json()["canExecute"] is False
    assert file_rows(world) == {int(cited["FILE_SN"])} and present(root, cited)


def test_기한이_안_된_파일만_있으면_건수는_0이고_예정일은_가장_이른_기한이다(
    world: World, root: Path
) -> None:
    stored(world, root, "a", MDFCN_DT=START - 10 * DAY)  # 20일 뒤
    stored(world, root, "b", MDFCN_DT=START - 25 * DAY)  # 5일 뒤
    stored(
        world, root, "c", REG_DT=START - 4 * YEAR, MDFCN_DT=START - 300 * DAY, **proof_owner(world)
    )  # 증빙은 1년 뒤
    operator(world)
    item = items(world)["FILE_ORIGINALS"]
    assert (item["count"], item["state"]) == (0, "WAITING")
    assert item["dueOn"] == ((START - 25 * DAY + timedelta(days=30) + timedelta(hours=9)).date()).isoformat()


def test_새벽_자동_정리가_원본과_행을_함께_지운다(world: World, root: Path) -> None:
    old = stored(world, root, "old")
    recent = stored(world, root, "recent", MDFCN_DT=START - 5 * DAY)
    world.db.commit()
    assert retention.purge_due(world.db, world.bundle, world.clock, str(root)) == 1
    assert file_rows(world) == {int(recent["FILE_SN"])}
    assert not present(root, old) and present(root, recent)
    jobs = (
        world.db.execute(
            text("SELECT TRGT_TBL_NM t, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='RETENTION_EXECUTE'")
        )
        .mappings()
        .all()
    )
    assert [(j["t"], j["c"]) for j in jobs] == [("TB_FILE", "처리 1건 [자동]")]
    assert retention.purge_due(world.db, world.bundle, world.clock, str(root)) == 0


def test_원본을_지우지_못하면_행을_남기고_실패를_알린다(world: World, root: Path) -> None:
    stuck = stored(world, root, "stuck")
    (root / str(stuck["STRG_KEY"])).unlink()
    (root / str(stuck["STRG_KEY"])).mkdir()  # 파일이 아니라 폴더라 지울 수 없다
    ((root / str(stuck["STRG_KEY"])) / "inside").write_bytes(b"x")
    world.db.commit()
    with pytest.raises(RuntimeError, match="FILE_ORIGINALS"):
        retention.purge_due(world.db, world.bundle, world.clock, str(root))
    assert file_rows(world) == {int(stuck["FILE_SN"])}  # 행이 남아 다음에 다시 한다


def test_원본이_이미_없으면_행만_지우고_넘어간다(world: World, root: Path) -> None:
    gone = stored(world, root, "gone")
    (root / str(gone["STRG_KEY"])).unlink()
    world.db.commit()
    assert retention.purge_due(world.db, world.bundle, world.clock, str(root)) == 1
    assert file_rows(world) == set()
