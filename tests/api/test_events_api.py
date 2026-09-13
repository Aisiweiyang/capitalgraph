"""变更事件流 API 集成测试：RBAC、参数校验、合成数据已知变更断言与确定性。

已知变更锚点（seed=42, entities=12）：合成数据的历史变更场景把某公司 60% 持股
在 2022-06-01 从一名自然人转移到另一名自然人（persons[0]→persons[1]），
因此 2022-01-01 → 2023-01-01 的全局事件流必含"持股失效 + 持股新增"各一条、
对象相同、比例均为 60%（该窗口内其余声明无变化）。
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
    db_path: Path = tmp_path_factory.mktemp("events-api") / "events-test.sqlite3"
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


def test_events_requires_auth(api, seeded):
    assert api.get("/api/v1/events").status_code == 401
    assert (
        api.get("/api/v1/events", params={"from": "2022-01-01", "to": "2023-01-01"}).status_code
        == 401
    )


def test_events_rejects_inverted_window(api, auth, seeded):
    resp = api.get(
        "/api/v1/events",
        params={"from": "2023-01-01", "to": "2022-01-01"},
        headers=auth["viewer"],
    )
    assert resp.status_code == 422


def test_transfer_window_yields_known_pair(api, auth, seeded):
    """2022-01-01→2023-01-01 窗口内：恰好"持股失效 + 持股新增"各一，对象相同、比例 60%。"""
    resp = api.get(
        "/api/v1/events",
        params={"from": "2022-01-01", "to": "2023-01-01"},
        headers=auth["viewer"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["from"] == "2022-01-01"
    assert body["to"] == "2023-01-01"
    assert body["total"] == 2, body
    types = sorted(e["event_type"] for e in body["events"])
    assert types == ["holding_added", "holding_removed"]
    added = next(e for e in body["events"] if e["event_type"] == "holding_added")
    removed = next(e for e in body["events"] if e["event_type"] == "holding_removed")
    assert added["object_id"] == removed["object_id"]
    assert added["after_percent"] == 60.0
    assert removed["before_percent"] == 60.0
    assert added["subject_id"] != removed["subject_id"]
    assert body["counts_by_type"]
    assert body["assumptions"]
    assert body["algorithm_version"].startswith("cg-events/")


def test_events_pagination_and_type_filter(api, auth, seeded):
    resp = api.get(
        "/api/v1/events",
        params={"from": "2022-01-01", "to": "2023-01-01", "limit": "1"},
        headers=auth["viewer"],
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 2
    assert body["returned"] == 1
    assert len(body["events"]) == 1
    # 类型筛选：只保留失效事件
    resp = api.get(
        "/api/v1/events",
        params={"from": "2022-01-01", "to": "2023-01-01", "event_type": "holding_removed"},
        headers=auth["viewer"],
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["events"][0]["event_type"] == "holding_removed"


def test_events_deterministic(api, auth, seeded):
    params = {"from": "2020-01-01", "to": "2024-01-01"}
    a = api.get("/api/v1/events", params=params, headers=auth["viewer"]).json()
    b = api.get("/api/v1/events", params=params, headers=auth["viewer"]).json()
    assert a == b


def test_entity_events_scoped(api, auth, seeded):
    listing = api.get(
        "/api/v1/events",
        params={"from": "2022-01-01", "to": "2023-01-01"},
        headers=auth["viewer"],
    ).json()
    added = next(e for e in listing["events"] if e["event_type"] == "holding_added")
    target_id = added["object_id"]
    resp = api.get(
        f"/api/v1/entities/{target_id}/events",
        params={"from": "2022-01-01", "to": "2023-01-01"},
        headers=auth["viewer"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity_id"] == target_id
    assert body["total"] == 2  # 该公司既是失效侧对象也是新增侧对象
    assert {e["event_type"] for e in body["events"]} == {"holding_added", "holding_removed"}
    for ev in body["events"]:
        assert target_id in (ev["subject_id"], ev["object_id"])
        assert ev["evidence_keys"]
    # 对方实体视角：只见单侧事件
    resp = api.get(
        f"/api/v1/entities/{added['subject_id']}/events",
        params={"from": "2022-01-01", "to": "2023-01-01"},
        headers=auth["viewer"],
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["events"][0]["event_type"] == "holding_added"


def test_entity_events_unknown_entity_404(api, auth, seeded):
    resp = api.get(
        "/api/v1/entities/nonexistent/events",
        params={"from": "2022-01-01", "to": "2023-01-01"},
        headers=auth["viewer"],
    )
    assert resp.status_code == 404


def test_event_types_catalog(api, auth, seeded):
    resp = api.get("/api/v1/events/types", headers=auth["viewer"])
    assert resp.status_code == 200
    labels = {row["event_type"]: row["label"] for row in resp.json()}
    assert labels["holding_ratio_changed"] == "持股比例增减"
    assert labels["control_gained"] == "控制权获得"
