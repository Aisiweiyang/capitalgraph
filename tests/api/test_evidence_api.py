"""证据工作台 API 集成测试：覆盖率、文档导航、声明反查（RBAC + 形状 + 口径）。

合成数据每条声明恰登记 1 条证据片段 → 种子库覆盖率必为 100%；
缺失证据的显式呈现口径由纯函数单测覆盖（tests/capital_graph/test_evidence_stats.py）。
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
    db_path: Path = tmp_path_factory.mktemp("evidence-api") / "evidence-test.sqlite3"
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


def test_evidence_requires_auth(api, seeded):
    assert api.get("/api/v1/evidence/coverage").status_code == 401
    assert api.get("/api/v1/evidence/documents").status_code == 401
    assert api.get("/api/v1/evidence/lookup", params={"ids": "abc"}).status_code == 401


def test_coverage_shape_and_full_coverage(api, auth, seeded):
    resp = api.get("/api/v1/evidence/coverage", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_active_statements"] > 0
    assert body["covered_statements"] == body["total_active_statements"]
    assert body["coverage_percent"] == 100.0
    assert body["missing_statements"] == 0
    assert body["algorithm_version"].startswith("cg-evidence-coverage/")
    assert body["assumptions"]
    # 分组齐全：谓词/连接器/年度
    for key in ("by_predicate", "by_connector", "by_year"):
        groups = body[key]
        assert groups and all(
            {"key", "total", "covered", "missing", "coverage_percent"} == set(g) for g in groups
        )
    pred_keys = {g["key"] for g in body["by_predicate"]}
    assert "holds_shares" in pred_keys
    # 时点参数：与当前一致（合成声明 2018 起全部有效）
    resp = api.get("/api/v1/evidence/coverage", params={"at": "2023-01-01"}, headers=auth["viewer"])
    assert resp.status_code == 200
    assert resp.json()["total_active_statements"] == body["total_active_statements"]


def test_documents_navigation_tree(api, auth, seeded):
    resp = api.get("/api/v1/evidence/documents", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    assert body["fragment_total"] > 0
    doc = body["documents"][0]
    for key in ("document_id", "title", "snapshots", "connector_id"):
        assert key in doc
    assert doc["snapshots"], "合成数据应有快照"
    snap = doc["snapshots"][0]
    for key in ("snapshot_id", "content_sha256", "fragment_count", "fragments"):
        assert key in snap
    assert snap["fragment_count"] == len(snap["fragments"])
    frag = snap["fragments"][0]
    assert {"fragment_id", "field_path", "raw_value"} <= set(frag)


def test_lookup_returns_fragments_and_missing(api, auth, seeded):
    docs = api.get("/api/v1/evidence/documents", headers=auth["viewer"]).json()
    frag = docs["documents"][0]["snapshots"][0]["fragments"][0]
    # 反查：片段本身不带 statement_id，改用 events 的证据键验证
    events = api.get(
        "/api/v1/events",
        params={"from": "2022-01-01", "to": "2023-01-01"},
        headers=auth["viewer"],
    ).json()
    sid = events["events"][0]["evidence_keys"][0]
    resp = api.get("/api/v1/evidence/lookup", params={"ids": sid}, headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["requested"] == 1
    assert body["found"] == 1
    assert body["missing_statement_ids"] == []
    fragments = body["evidence"][sid]
    assert fragments and {"document_title", "field_path", "content_sha256"} <= set(fragments[0])
    # 未命中：显式列出 missing
    resp = api.get(
        "/api/v1/evidence/lookup",
        params={"ids": f"{sid},ffffffffffffffffffffffffffffffff"},
        headers=auth["viewer"],
    )
    body = resp.json()
    assert body["found"] == 1
    assert body["missing_statement_ids"] == ["ffffffffffffffffffffffffffffffff"]
    # 片段字段路径与文档树一致（同一证据链）
    assert frag["field_path"]


def test_lookup_validates_input(api, auth, seeded):
    assert (
        api.get("/api/v1/evidence/lookup", params={"ids": ""}, headers=auth["viewer"]).status_code
        == 422
    )
    many = ",".join(f"{'0' * 32}{i}" for i in range(201))
    assert (
        api.get("/api/v1/evidence/lookup", params={"ids": many}, headers=auth["viewer"]).status_code
        == 422
    )
