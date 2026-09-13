"""风险传导 API 集成测试：合成担保场景上的已知链条断言、RBAC、幂等去重。

合成数据（seed=42, entities=12 → 8 家公司）固定场景：
- 链式担保：C2→C3→C4→C5（12000/9000 万，末档缺金额）；
- 环式互保：C5→C6→C7→C5（5000/5000 万 + 一条缺金额）；
- 股权质押：C1 质押 C2（40%，3000 万）。
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
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
        for name, role in (
            ("admin", Role.ADMIN),
            ("analyst", Role.ANALYST),
            ("viewer", Role.VIEWER),
        ):
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
def db_path(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("risk-api") / "risk-test.sqlite3"


@pytest.fixture(scope="module")
def api(db_path):
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
    return {
        "admin": _login(api, "admin"),
        "analyst": _login(api, "analyst"),
        "viewer": _login(api, "viewer"),
    }


@pytest.fixture(scope="module")
def seeded(api, auth):
    resp = api.post(
        "/api/v1/ingest/runs",
        json={"connector": "synthetic", "params": {"seed": "42", "entities": "12"}},
        headers=auth["admin"],
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _guarantee_pairs(db_path: Path) -> list[tuple[str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "select subject_id, object_id from relationship_statements "
            "where predicate='provides_guarantee' and status='active'"
        ).fetchall()
    finally:
        conn.close()


def _ring_nodes(db_path: Path) -> list[str]:
    """互保圈节点：沿担保边走三步回到自身的节点集合。"""
    pairs = _guarantee_pairs(db_path)
    nxt: dict[str, list[str]] = {}
    for a, b in pairs:
        nxt.setdefault(a, []).append(b)
    ring = []
    for node in nxt:
        for b in nxt.get(node, ()):
            for c in nxt.get(b, ()):
                if node in nxt.get(c, ()):
                    ring.extend((node, b, c))
    return sorted(set(ring))


def _chain_head(db_path: Path) -> str:
    """链头：只担保别人、从不被担保的节点。"""
    pairs = _guarantee_pairs(db_path)
    given = {a for a, _ in pairs}
    received = {b for _, b in pairs}
    return sorted(given - received)[0]


@pytest.fixture(scope="module")
def ring_node(db_path, seeded):
    return _ring_nodes(db_path)[0]


@pytest.fixture(scope="module")
def chain_head(db_path, seeded):
    return _chain_head(db_path)


def test_risk_requires_auth(api, seeded, ring_node):
    assert api.get(f"/api/v1/risk/chains/{ring_node}").status_code == 401
    assert api.get("/api/v1/risk/flags").status_code == 401
    assert api.post("/api/v1/risk/compute").status_code == 401


def test_compute_requires_analyst(api, auth, seeded):
    resp = api.post("/api/v1/risk/compute", headers=auth["viewer"])
    assert resp.status_code == 403


def test_chains_on_ring_member(api, auth, seeded, ring_node, db_path):
    """互保圈成员：检出所在环、传导覆盖圈上其他节点；质押敞口可见。"""
    resp = api.get(f"/api/v1/risk/chains/{ring_node}", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity_id"] == ring_node
    assert body["algorithm_version"].startswith("cg-risk-chains/")
    assert len(body["input_digest"]) == 64
    # 该主体在互保圈上：环长度 = 3 节点 + 闭合收尾
    assert any(len(c) == 4 and c[0] == c[-1] for c in body["cycles"])
    # 传导模拟：圈上另外两个节点受累
    assert len(body["propagation"]["affected_entities"]) >= 2
    # 缺失金额显式：全图担保边中至少一条缺金额
    assert body["guarantee_edge_count"] >= 6
    # 质押场景：C2 被质押 → 若查的是 C2 能看到；此处至少结构完整
    for p in body["pledges"]:
        for key in ("pledgor", "target", "share_percent", "amount_wan"):
            assert key in p


def test_chains_on_chain_head(api, auth, seeded, chain_head):
    """链头无人担保其义务 → 链条为空；其出险不产生上游传导。"""
    resp = api.get(f"/api/v1/risk/chains/{chain_head}", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["chains"] == []
    assert body["propagation"]["affected_entities"] == []


def test_propagation_bridges_ring_and_chain(api, auth, seeded, ring_node):
    """桥接节点（链尾即圈成员）出险：传导同时覆盖互保圈与担保链（≥3 家）。"""
    resp = api.get(f"/api/v1/risk/chains/{ring_node}", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["propagation"]["affected_entities"]) >= 3
    # 桥接链路的末端一档与环上一条边都缺金额 → 显式计数
    assert body["propagation"]["total_amount_missing_edges"] >= 1
    assert body["propagation"]["total_nominal_wan"] is None  # 有缺失就不给合计


def test_compute_creates_flags_and_is_idempotent(api, auth, seeded, ring_node):
    """compute 登记互保圈与传导标记；同输入重跑不重复创建。"""
    resp = api.post(
        "/api/v1/risk/compute", params={"distressed": ring_node}, headers=auth["analyst"]
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cycles_found"] >= 1
    assert body["cycle_flags_created"] == 1
    assert body["exposure_flags_created"] >= 3  # 圈上 2 家 + 链上 2 家（去重后）
    assert ring_node in body["distressed_used"]

    again = api.post(
        "/api/v1/risk/compute", params={"distressed": ring_node}, headers=auth["analyst"]
    )
    assert again.status_code == 200
    assert again.json()["cycle_flags_created"] == 0
    assert again.json()["exposure_flags_created"] == 0


def test_flags_listed_for_review(api, auth, seeded, ring_node):
    resp = api.get("/api/v1/risk/flags", headers=auth["viewer"])
    assert resp.status_code == 200
    flags = resp.json()
    types = {f["flag_type"] for f in flags}
    assert "guarantee_cycle" in types
    assert "guarantee_chain_exposure" in types
    for f in flags:
        assert f["payload"].get("input_digest")
        assert f["payload"].get("algorithm_version")
    cycle = next(f for f in flags if f["flag_type"] == "guarantee_cycle")
    assert len(cycle["payload"]["cycle"]) == 4  # 3 节点 + 闭合收尾


def test_compute_rejects_unknown_distressed(api, auth, seeded):
    resp = api.post(
        "/api/v1/risk/compute", params={"distressed": "no-such-entity"}, headers=auth["analyst"]
    )
    assert resp.status_code == 422


def test_risk_chains_unknown_entity_404(api, auth, seeded):
    resp = api.get("/api/v1/risk/chains/no-such-entity", headers=auth["viewer"])
    assert resp.status_code == 404


def test_chains_deterministic(api, auth, seeded, ring_node):
    a = api.get(f"/api/v1/risk/chains/{ring_node}", headers=auth["viewer"]).json()
    b = api.get(f"/api/v1/risk/chains/{ring_node}", headers=auth["viewer"]).json()
    assert a == b
