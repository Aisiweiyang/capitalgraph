"""系族 API 集成测试：RBAC、参数校验、合成数据上的已知系族断言与确定性。"""

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
    db_path: Path = tmp_path_factory.mktemp("families-api") / "families-test.sqlite3"
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


def test_families_requires_auth(api, seeded):
    assert api.get("/api/v1/families").status_code == 401
    assert api.get("/api/v1/families/flows").status_code == 401


def test_families_viewer_can_read(api, auth, seeded):
    resp = api.get("/api/v1/families", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    assert body["algorithm_version"].startswith("cg-families/")
    assert len(body["config_hash"]) == 64
    fam = body["families"][0]
    for key in (
        "family_id",
        "controllers",
        "controller_names",
        "member_count",
        "region_coverage",
        "cycle_count",
        "density",
    ):
        assert key in fam
    # 合成数据中自然人为控制人：控制人应为 person 类型且成员 ≥ 2
    assert fam["member_count"] >= 2


def test_families_deterministic_responses(api, auth, seeded):
    a = api.get("/api/v1/families", headers=auth["viewer"]).json()
    b = api.get("/api/v1/families", headers=auth["viewer"]).json()
    assert a == b


def test_families_sort_by_variants(api, auth, seeded):
    for sort in ("size", "regions", "cycles"):
        resp = api.get("/api/v1/families", params={"sort_by": sort}, headers=auth["viewer"])
        assert resp.status_code == 200
    bad = api.get("/api/v1/families", params={"sort_by": "bogus"}, headers=auth["viewer"])
    assert bad.status_code == 422


def test_families_param_validation(api, auth, seeded):
    resp = api.get(
        "/api/v1/families", params={"min_control_ratio_percent": 101}, headers=auth["viewer"]
    )
    assert resp.status_code == 422


def test_family_detail_members_and_paths(api, auth, seeded):
    lst = api.get("/api/v1/families", headers=auth["viewer"]).json()
    root = lst["families"][0]["family_id"]
    resp = api.get(f"/api/v1/families/{root}", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["family_id"] == root
    assert body["member_count"] == len(body["members"])
    for member in body["members"]:
        assert (
            member["path"][0] in body["controllers"] or member["entity_id"] in body["controllers"]
        )
        assert len(member["path_names"]) == len(member["path"])
    assert body.get("assumptions")
    # 确定性：再次请求全等
    again = api.get(f"/api/v1/families/{root}", headers=auth["viewer"]).json()
    assert again == body


def test_family_detail_unknown_root_404(api, auth, seeded):
    resp = api.get("/api/v1/families/nonexistent-entity", headers=auth["viewer"])
    assert resp.status_code == 404


def test_families_flows_shape(api, auth, seeded):
    resp = api.get("/api/v1/families/flows", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    for key in ("rows", "intra_family_edges", "ungrouped_edges", "family_names", "count"):
        assert key in body
    for row in body["rows"]:
        assert row["from_family"] != row["to_family"]
        # 缺失金额显式：amount_wan 为 None 时必须有缺失计数
        if row["amount_wan"] is None:
            assert row["amount_missing_edges"] == row["edge_count"]
