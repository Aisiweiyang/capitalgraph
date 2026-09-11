"""API 集成测试：认证、RBAC、检索、穿透、时间点、限流、注入防护。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from cg_api.main import create_app
from cg_api.routers.penetration import _escape_csv_cell
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
def api(tmp_path_factory):
    db_path: Path = tmp_path_factory.mktemp("api") / "api-test.sqlite3"
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


def test_login_wrong_password(api):
    resp = api.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user(api):
    resp = api.post("/api/v1/auth/login", json={"username": "ghost", "password": "whatever1"})
    assert resp.status_code == 401


def test_anonymous_denied(api):
    assert api.get("/api/v1/entities/search?q=x").status_code == 401
    assert api.get("/api/v1/audit").status_code == 401


def test_rbac_hierarchy(api, auth, seeded):
    # viewer 不能运行采集
    resp = api.post(
        "/api/v1/ingest/runs", json={"connector": "synthetic", "params": {}}, headers=auth["viewer"]
    )
    assert resp.status_code == 403
    # viewer 可以检索
    assert (
        api.get("/api/v1/entities/search", params={"q": "公司"}, headers=auth["viewer"]).status_code
        == 200
    )
    # analyst 可以采集但不能看审计
    assert api.get("/api/v1/audit", headers=auth["analyst"]).status_code == 403
    assert api.get("/api/v1/audit", headers=auth["admin"]).status_code == 200


def test_search_finds_company(api, auth, seeded):
    resp = api.get("/api/v1/entities/search", params={"q": "有限公司"}, headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 5


def test_search_sql_injection_is_safe(api, auth):
    resp = api.get(
        "/api/v1/entities/search",
        params={"q": "'; DROP TABLE entities; --"},
        headers=auth["viewer"],
    )
    assert resp.status_code == 200
    # 表还在（参数化查询）
    ok = api.get("/api/v1/entities/search", params={"q": "公司"}, headers=auth["viewer"])
    assert ok.status_code == 200


def test_penetration_flow_with_ubo_and_cycle(api, auth, seeded):
    resp = api.get(
        "/api/v1/entities/search", params={"q": "有限公司", "limit": 50}, headers=auth["viewer"]
    )
    hits = resp.json()["hits"]
    assert hits
    target = hits[0]
    detail = api.get(f"/api/v1/entities/{target['id']}", headers=auth["viewer"]).json()
    assert detail["identifiers"]

    pen = api.get(f"/api/v1/penetration/{target['id']}", headers=auth["viewer"])
    assert pen.status_code == 200
    body = pen.json()
    assert body["root"] == target["id"]
    assert body["aggregates"]
    assert body["assumptions"]
    assert body["algorithm_version"].startswith("cg-penetration/")
    for ubo in body["ubo_candidates"]:
        assert ubo["basis"]
        # 候选必须附证据声明
        assert ubo["statement_ids"]


def test_time_point_query_changes_answer(api, auth, seeded):
    # 合成数据把历史股东变更放在最后一个公司 C0007；标识符检索应能找到
    resp = api.get(
        "/api/v1/entities/search",
        params={"q": "C0007"},
        headers=auth["viewer"],
    )
    assert resp.json()["total"] == 1  # 按来源内部 ID 检索命中
    target_id = resp.json()["hits"][0]["id"]

    before = api.get(
        f"/api/v1/entities/{target_id}/shareholders",
        params={"at": "2020-01-01"},
        headers=auth["viewer"],
    ).json()
    after = api.get(
        f"/api/v1/entities/{target_id}/shareholders",
        params={"at": "2023-01-01"},
        headers=auth["viewer"],
    ).json()
    # 历史变更语义：持股 60% 的主体在 2022-06-01 发生更替
    big_before = [s for s in before["shareholders"] if s["share_ratio_percent"] == 60.0]
    big_after = [s for s in after["shareholders"] if s["share_ratio_percent"] == 60.0]
    assert big_before and big_after, "两个时点都应存在 60% 持股人"
    assert big_before[0]["shareholder_id"] != big_after[0]["shareholder_id"], "60% 持股人应已更替"
    # 当前状态不覆盖历史：历史查询仍能看到旧声明
    history = api.get(f"/api/v1/entities/{target_id}/history", headers=auth["viewer"]).json()
    assert len(history["statements"]) >= 2


def test_ingest_idempotent_second_run(api, auth, seeded):
    resp = api.post(
        "/api/v1/ingest/runs",
        json={"connector": "synthetic", "params": {"seed": "42", "entities": "12"}},
        headers=auth["analyst"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "idempotent_hit"


def test_unknown_connector_404(api, auth):
    resp = api.post("/api/v1/ingest/runs", json={"connector": "nope"}, headers=auth["analyst"])
    assert resp.status_code == 404


def test_csv_export(api, auth, seeded):
    hits = api.get(
        "/api/v1/entities/search", params={"q": "有限公司", "limit": 5}, headers=auth["viewer"]
    ).json()["hits"]
    resp = api.get(f"/api/v1/penetration/{hits[0]['id']}/export.csv", headers=auth["viewer"])
    assert resp.status_code == 200
    assert resp.text.startswith("\ufeff")  # BOM
    assert "有效权益" in resp.text


def test_csv_formula_escape():
    assert _escape_csv_cell("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
    assert _escape_csv_cell("+1+1") == "'+1+1"
    assert _escape_csv_cell("正常文本") == "正常文本"


def test_rate_limit_429():
    os.environ["CG_RATE_LIMIT_PER_MINUTE"] = "5"
    try:
        client = TestClient(create_app())
        with client:
            codes = [
                client.post(
                    "/api/v1/auth/login", json={"username": "x", "password": "y"}
                ).status_code
                for _ in range(10)
            ]
        assert 429 in codes
    finally:
        os.environ.pop("CG_RATE_LIMIT_PER_MINUTE", None)


def test_audit_trail_records_actions(api, auth, seeded):
    resp = api.get("/api/v1/audit", headers=auth["admin"])
    actions = [row["action"] for row in resp.json()]
    assert "auth.login" in actions
    assert "ingest.run" in actions


def test_admin_create_user_and_login(api, auth):
    resp = api.post(
        "/api/v1/admin/users",
        json={"username": "tempuser", "password": "tempuser-pass-123", "role": "viewer"},
        headers=auth["admin"],
    )
    assert resp.status_code == 200
    login = api.post(
        "/api/v1/auth/login", json={"username": "tempuser", "password": "tempuser-pass-123"}
    )
    assert login.status_code == 200
    # 弱口令拒绝
    weak = api.post(
        "/api/v1/admin/users",
        json={"username": "weakling", "password": "short", "role": "viewer"},
        headers=auth["admin"],
    )
    assert weak.status_code == 422


def test_stats_overview_aggregates(api, auth, seeded):
    resp = api.get("/api/v1/stats", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["entities_total"] >= 12
    assert body["statements_total"] > 0
    # 分布计数与总量自洽
    assert sum(body["entities_by_kind"].values()) == body["entities_total"]
    assert sum(body["statements_by_predicate"].values()) == body["statements_total"]
    assert sum(body["statements_by_year"].values()) == body["statements_total"]
    assert body["sources_total"] > 0
    assert body["runs_total"] >= 1
    assert body["last_run"]["connector_id"] == "synthetic"


def test_stats_requires_auth(api):
    assert api.get("/api/v1/stats").status_code == 401


def test_flows_regions_aggregates_seeded_data(api, auth, seeded):
    resp = api.get("/api/v1/flows/regions", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] > 0
    flow = body["flows"][0]
    assert flow["from_region"] != flow["to_region"]
    assert flow["edge_count"] >= 1
    assert flow["amount_wan"] is not None


def test_flows_summary_metrics(api, auth, seeded):
    resp = api.get("/api/v1/flows/summary", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["regions"]) >= 2
    assert body["hhi"] is not None and 0 < body["hhi"] <= 10000
    assert body["total_cross_amount_wan"] > 0
    assert body["cycles"]["cycle_count"] >= 1  # 合成数据含 C0↔C1 环
    net_sum = sum(r["net_wan"] for r in body["regions"])
    assert abs(net_sum) < 0.01  # 净额守恒：流入之和 = 流出之和


def test_flows_timeline_and_industries(api, auth, seeded):
    timeline = api.get("/api/v1/flows/timeline", headers=auth["viewer"]).json()
    assert timeline["timeline"] and timeline["timeline"][0]["year"] >= 2018
    industries = api.get("/api/v1/flows/industries", headers=auth["viewer"]).json()
    assert industries["rows"], "合成数据的企业均有行业，应产生省→行业聚合"


def test_flows_requires_auth(api):
    assert api.get("/api/v1/flows/summary").status_code == 401
