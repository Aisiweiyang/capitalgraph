"""格局对比 API 集成测试：RBAC、参数校验、合成数据已知格局变化断言与确定性。

已知锚点（seed=42, entities=12）：2022-06-01 的 60% 持股转移使目标公司在
from（2022-01-01）与 to（2023-01-01）两个时点间更换控制人（原持有人 60% 持股
失效构成控制边，新持有人 60% 生效构成控制边），因此系族格局必有变化；
区域流动至少有一条流向对的边数/存在性发生变化。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from cg_api.main import create_app
from fastapi.testclient import TestClient

os.environ.setdefault("CG_ENV", "test")


async def _prepare_db(db_path: Path) -> None:
    from argon2 import PasswordHasher
    from cg_domain.db import make_engine, make_session_factory
    from cg_domain.enums import Role
    from cg_domain.orm import Base, User

    engine = make_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    hasher = PasswordHasher()
    factory = make_session_factory(engine)
    async with factory() as session:
        for name, role in (("admin", Role.ADMIN), ("viewer", Role.VIEWER)):
            session.add(
                User(
                    username=name,
                    password_hash=hasher.hash(f"{name}-demo-password"),
                    role=role.value,
                )
            )
        await session.commit()
    await engine.dispose()


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    db_path: Path = tmp_path_factory.mktemp("compare-api") / "compare-test.sqlite3"
    os.environ["CG_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    asyncio.run(_prepare_db(db_path))
    client = TestClient(create_app())
    with client:
        yield client


def _login(client: TestClient, username: str) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": f"{username}-demo-password"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def auth(api):
    return {"admin": _login(api, "admin"), "viewer": _login(api, "viewer")}


@pytest.fixture(scope="module")
def seeded(api, auth):
    resp = api.post(
        "/api/v1/ingest/runs",
        json={"connector": "synthetic", "params": {"seed": "42", "entities": "12"}},
        headers=auth["admin"],
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


WINDOW = {"from": "2022-01-01", "to": "2023-01-01"}


def test_compare_requires_auth(api, seeded):
    assert api.get("/api/v1/families/compare", params=WINDOW).status_code == 401
    assert api.get("/api/v1/flows/compare", params=WINDOW).status_code == 401


def test_compare_rejects_inverted_window(api, auth, seeded):
    assert (
        api.get(
            "/api/v1/families/compare",
            params={"from": "2023-01-01", "to": "2022-01-01"},
            headers=auth["viewer"],
        ).status_code
        == 422
    )
    assert (
        api.get(
            "/api/v1/flows/compare",
            params={"from": "2023-01-01", "to": "2022-01-01"},
            headers=auth["viewer"],
        ).status_code
        == 422
    )


def test_families_compare_known_change(api, auth, seeded):
    resp = api.get("/api/v1/families/compare", params=WINDOW, headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["from"] == "2022-01-01" and body["to"] == "2023-01-01"
    assert body["algorithm_version"].startswith("cg-compare/")
    # 60% 持股转移必引起系族格局变化（成员/控制人在族间移动或族增减）
    has_change = bool(body["added_families"] or body["removed_families"] or body["changed"])
    assert has_change, body
    for row in body["changed"]:
        assert (
            row["members_added"]
            or row["members_removed"]
            or row["controllers_added"]
            or row["controllers_removed"]
        )
        assert len(row["members_added_names"]) == len(row["members_added"])
        assert "family_name" in row
    assert body["assumptions"]


def test_families_compare_identical_window_zero_diff(api, auth, seeded):
    params = {"from": "2023-01-01", "to": "2023-01-01"}
    resp = api.get("/api/v1/families/compare", params=params, headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["added_families"] == []
    assert body["removed_families"] == []
    assert body["changed"] == []
    assert body["family_count"]["delta"] == 0


def test_families_compare_deterministic(api, auth, seeded):
    a = api.get("/api/v1/families/compare", params=WINDOW, headers=auth["viewer"]).json()
    b = api.get("/api/v1/families/compare", params=WINDOW, headers=auth["viewer"]).json()
    assert a == b


def test_flows_compare_shape_and_consistency(api, auth, seeded):
    resp = api.get("/api/v1/flows/compare", params=WINDOW, headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    for key in ("totals", "flows_added", "flows_removed", "flows_changed", "assumptions"):
        assert key in body
    totals = body["totals"]
    assert set(totals["flow_count"]) == {"before", "after", "delta"}
    assert set(totals["hhi"]) == {"before", "after", "delta"}
    # 一致性：流向对数量变化 = 新增数 - 消失数
    assert body["flow_pair_delta_check"] is True
    assert totals["flow_count"]["after"] - totals["flow_count"]["before"] == len(
        body["flows_added"]
    ) - len(body["flows_removed"])
    # 转移发生在 2022-06-01 → 该窗口必有流向对增减或变化（人数区域不同）
    assert body["flows_added"] or body["flows_removed"] or body["flows_changed"], body


def test_flows_compare_deterministic(api, auth, seeded):
    a = api.get("/api/v1/flows/compare", params=WINDOW, headers=auth["viewer"]).json()
    b = api.get("/api/v1/flows/compare", params=WINDOW, headers=auth["viewer"]).json()
    assert a == b
