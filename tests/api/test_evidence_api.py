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


# ---------------------------------------------- v0.6 切片 A：覆盖率趋势（ADR-019）


def test_coverage_timeline_requires_auth(api, seeded):
    assert api.get("/api/v1/evidence/coverage/timeline").status_code == 401


def test_coverage_timeline_shape_and_known_years(api, auth, seeded):
    resp = api.get("/api/v1/evidence/coverage/timeline", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["algorithm_version"].startswith("cg-evidence-timeline/")
    assert body["assumptions"]
    tl = body["timeline"]
    assert tl, "种子库应有年度分组"
    assert all(
        {"year", "total", "covered", "missing", "coverage_percent", "delta_vs_prev"} == set(r)
        for r in tl
    )
    years = [r["year"] for r in tl]
    assert years == sorted(years), "趋势按年度升序"
    assert 2018 in years, "合成声明 valid_from=2018-01-01"
    # 种子库每条声明恰有 1 条证据 → 各年覆盖率 100%，缺失为 0
    assert all(r["covered"] == r["total"] and r["missing"] == 0 for r in tl)
    assert tl[0]["delta_vs_prev"] is None
    # 与 /coverage 的按年度分组口径一致
    cov = api.get("/api/v1/evidence/coverage", headers=auth["viewer"]).json()
    assert {r["year"]: r["total"] for r in tl} == {g["key"]: g["total"] for g in cov["by_year"]}


def test_coverage_timeline_at_filter(api, auth, seeded):
    # 时点 2021-01-01：2022-06-01 生效的转移声明不参与
    resp = api.get(
        "/api/v1/evidence/coverage/timeline", params={"at": "2021-01-01"}, headers=auth["viewer"]
    )
    assert resp.status_code == 200
    tl = resp.json()["timeline"]
    assert all(r["year"] <= 2021 for r in tl)
    cov21 = api.get(
        "/api/v1/evidence/coverage", params={"at": "2021-01-01"}, headers=auth["viewer"]
    ).json()
    assert {r["year"]: r["total"] for r in tl} == {g["key"]: g["total"] for g in cov21["by_year"]}


def test_coverage_embeds_timeline_matching_standalone(api, auth, seeded):
    """v0.6.1：/coverage 与统计共用同一次扫描附带 timeline，减少工作台重复请求。"""
    cov = api.get("/api/v1/evidence/coverage", headers=auth["viewer"])
    assert cov.status_code == 200
    tl_only = api.get("/api/v1/evidence/coverage/timeline", headers=auth["viewer"]).json()
    assert cov.json()["timeline"] == tl_only["timeline"]


# ---------------------------------------- v0.6 切片 B：证据时效规则（ADR-020）


def test_staleness_requires_auth(api, seeded):
    assert api.get("/api/v1/evidence/staleness").status_code == 401
    assert api.post("/api/v1/evidence/staleness/scan").status_code == 401


def test_staleness_viewer_can_read_scan_forbidden(api, auth, seeded):
    resp = api.get("/api/v1/evidence/staleness", headers=auth["viewer"])
    assert resp.status_code == 200
    assert api.post("/api/v1/evidence/staleness/scan", headers=auth["viewer"]).status_code == 403


def test_staleness_query_shape_and_validation(api, auth, seeded):
    resp = api.get("/api/v1/evidence/staleness", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "at",
        "years",
        "cutoff",
        "algorithm_version",
        "stale_count",
        "stale_candidates",
        "assumptions",
    ):
        assert key in body
    assert body["algorithm_version"].startswith("cg-evidence-staleness/")
    for bad_years in ("0", "31"):
        assert (
            api.get(
                "/api/v1/evidence/staleness", params={"years": bad_years}, headers=auth["viewer"]
            ).status_code
            == 422
        )


def test_staleness_known_pledge_hit(api, auth, seeded):
    """种子库仅质押演示声明回填 captured_at=2019-01-01 → 默认阈值下恰有 1 条候选。"""
    resp = api.get(
        "/api/v1/evidence/staleness",
        params={"at": "2024-01-02", "years": 5},
        headers=auth["viewer"],
    )
    body = resp.json()
    assert body["stale_count"] == 1
    cand = body["stale_candidates"][0]
    assert cand["predicate"] == "pledges_shares"
    assert cand["last_captured_at"].startswith("2019-01-01")
    assert cand["age_years"] > 4
    # 边界：at=2024-01-01 → cutoff 恰为 2019-01-01，等于不算陈旧
    resp = api.get(
        "/api/v1/evidence/staleness", params={"at": "2024-01-01"}, headers=auth["viewer"]
    )
    assert resp.json()["stale_count"] == 0


def test_staleness_scan_idempotent_and_audited(api, auth, seeded):
    resp = api.post(
        "/api/v1/evidence/staleness/scan",
        params={"at": "2024-01-02", "years": 5},
        headers=auth["admin"],
    )
    assert resp.status_code == 200
    first = resp.json()
    assert first["rule_name"] == "stale_source"
    assert first["total_candidates"] == 1
    assert first["created"] == 1 and first["skipped"] == 0
    # 二扫幂等：同 (rule_name, statement_id) open 去重
    second = api.post(
        "/api/v1/evidence/staleness/scan",
        params={"at": "2024-01-02", "years": 5},
        headers=auth["admin"],
    ).json()
    assert second["created"] == 0 and second["skipped"] == 1
    # 复核通道（数据质量问题表）可见，detail 带阈值与取证时间
    issues = api.get("/api/v1/quality/issues", headers=auth["viewer"]).json()
    stale = [q for q in issues if q["rule_name"] == "stale_source"]
    assert len(stale) == 1
    assert stale[0]["statement_id"]
    assert stale[0]["detail"]["years"] == 5
    assert stale[0]["detail"]["last_captured_at"].startswith("2019-01-01")
    # 扫描写审计
    audit = api.get("/api/v1/audit", headers=auth["admin"]).json()
    assert any(a["action"] == "evidence.staleness_scan" for a in audit)


def test_staleness_scan_validates_years(api, auth, seeded):
    assert (
        api.post(
            "/api/v1/evidence/staleness/scan", params={"years": 0}, headers=auth["admin"]
        ).status_code
        == 422
    )


# ---------------------------------------- v0.7 质量规则族（ADR-021）


def test_quality_requires_auth(api, seeded):
    assert api.get("/api/v1/evidence/quality").status_code == 401


def test_quality_overview_shape_and_known_counts(api, auth, seeded):
    resp = api.get("/api/v1/evidence/quality", headers=auth["viewer"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["algorithm_version"].startswith("cg-evidence-quality/")
    assert body["assumptions"]
    # 五维度计数齐备，且与既有单规则端点同源同值
    stale = api.get(
        "/api/v1/evidence/staleness", params={"years": 5}, headers=auth["viewer"]
    ).json()
    cov = api.get("/api/v1/evidence/coverage", headers=auth["viewer"]).json()
    assert body["counts"]["staleness"] == stale["stale_count"]
    assert body["counts"]["coverage_missing"] == cov["missing_statements"]
    assert body["total_candidates"] == sum(body["counts"].values())
    # 合成库已知候选（seed=42 确定性）：转移场景同键两条 holds_shares 构成唯一性候选；
    # USCC 全部合法；单连接器无跨源冲突
    assert body["validity"]["checked"] > 0
    assert body["validity"]["invalid_count"] == 0
    assert body["uniqueness"]["group_count"] == 1
    assert all(len(g["statement_ids"]) >= 2 for g in body["uniqueness"]["groups"])
    assert body["consistency"]["conflict_count"] == 0


def test_quality_catches_invalid_identifier(api, auth, seeded):
    """直接注入一条校验位非法的 uscc 标识符，有效性规则必须捕获。"""
    import os
    import sqlite3

    db_url = os.environ["CG_DATABASE_URL"]
    db_path = db_url.split("///", 1)[1]
    conn = sqlite3.connect(db_path)
    try:
        entity_id = conn.execute("SELECT id FROM entities LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO entity_identifiers (id, entity_id, namespace, value, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
            ("baduscc0000000000000000000000a", entity_id, "uscc", "91110000XXXXXXXXXX"),
        )
        conn.commit()
        total = conn.execute(
            "SELECT COUNT(*) FROM entity_identifiers WHERE namespace='uscc'"
        ).fetchone()[0]
    finally:
        conn.close()

    body = api.get("/api/v1/evidence/quality", headers=auth["viewer"]).json()
    assert body["validity"]["checked"] == total
    assert {"entity_id": entity_id, "value": "91110000XXXXXXXXXX"} in body["validity"]["invalid"]


def test_quality_uniqueness_flags_duplicate_statement(api, auth, seeded):
    """注入同键第二条 active 声明（不同连接器、不同比例），唯一性与一致性同时捕获。"""
    import os
    import sqlite3

    db_path = os.environ["CG_DATABASE_URL"].split("///", 1)[1]
    conn = sqlite3.connect(db_path)
    try:
        sid, sub, obj, pred = conn.execute(
            "SELECT id, subject_id, object_id, predicate FROM relationship_statements "
            "WHERE status='active' LIMIT 1"
        ).fetchone()
        dup_id = "dupstmt0000000000000000000000a"
        conn.execute(
            "INSERT INTO relationship_statements "
            "(id, subject_id, predicate, object_id, valid_from, status, connector_id, "
            "share_ratio_scaled, recorded_at, claim_basis, confidence, source_url, note) "
            "VALUES (?, ?, ?, ?, '2000-01-01', 'active', 'other-conn', 51000000, "
            "datetime('now'), 'normalized', 1.0, 'internal://test', '')",
            (dup_id, sub, pred, obj),
        )
        conn.commit()
    finally:
        conn.close()

    body = api.get("/api/v1/evidence/quality", headers=auth["viewer"]).json()
    assert body["uniqueness"]["group_count"] >= 1
    groups = [g for g in body["uniqueness"]["groups"] if sid in g["statement_ids"]]
    assert groups and dup_id in groups[0]["statement_ids"]
    assert body["consistency"]["conflict_count"] >= 1


# ---------------------------------------- v0.8 质量登记闭环（ADR-021 修订）

_BAD_SCAN_SEQ = 0


def _inject_bad_identifier(api):
    """向一个全新实体注入校验位非法的 uscc（每次唯一，实体级幂等不互扰）。"""
    global _BAD_SCAN_SEQ
    import os
    import sqlite3

    _BAD_SCAN_SEQ += 1
    db_path = os.environ["CG_DATABASE_URL"].split("///", 1)[1]
    conn = sqlite3.connect(db_path)
    try:
        entity_id = conn.execute(
            "SELECT id FROM entities ORDER BY id LIMIT 1 OFFSET ?", (_BAD_SCAN_SEQ,)
        ).fetchone()[0]
        value = f"91110000YYYYYYYY{_BAD_SCAN_SEQ:02d}"
        conn.execute(
            "INSERT INTO entity_identifiers (id, entity_id, namespace, value, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (f"badqccscan{_BAD_SCAN_SEQ:022d}", entity_id, "uscc", value),
        )
        conn.commit()
    finally:
        conn.close()
    return entity_id, value


def test_quality_scan_rbac(api, seeded, auth):
    assert api.post("/api/v1/evidence/quality/scan").status_code == 401
    assert api.post("/api/v1/evidence/quality/scan", headers=auth["viewer"]).status_code == 403
    assert api.post("/api/v1/evidence/quality/scan", headers=auth["analyst"]).status_code == 200


def test_quality_scan_registers_and_is_idempotent(api, seeded, auth):
    """新注入候选必被登记（增量精确断言）；二扫全部跳过（幂等，与库历史状态无关）。"""
    first = api.post("/api/v1/evidence/quality/scan", headers=auth["analyst"])
    assert first.status_code == 200

    entity_id, value = _inject_bad_identifier(api)
    second = api.post("/api/v1/evidence/quality/scan", headers=auth["analyst"])
    assert second.status_code == 200
    body = second.json()
    assert body["by_rule"]["identifier_validity"] == 1, "新实体的非法 uscc 必须登记"
    assert body["by_rule"]["duplicate_statement"] == 0, "既有候选不得重复登记"
    assert body["by_rule"]["cross_source_conflict"] == 0
    assert body["skipped"] >= 0 and body["created"] >= 1

    third = api.post("/api/v1/evidence/quality/scan", headers=auth["analyst"])
    assert third.status_code == 200
    body3 = third.json()
    assert body3["created"] == 0, "同候选不得重复登记"
    assert body3["skipped"] == body3["total_candidates"]
    assert set(body3["rule_names"]) == {
        "identifier_validity",
        "duplicate_statement",
        "cross_source_conflict",
    }
    assert entity_id and value


def test_quality_scan_audit_written(api, seeded, auth):
    import os
    import sqlite3

    api.post("/api/v1/evidence/quality/scan", headers=auth["analyst"])
    db_path = os.environ["CG_DATABASE_URL"].split("///", 1)[1]
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='evidence.quality_scan'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert row >= 1, "扫描必须写审计日志"


# ---------------------------------------- v0.9 真实公告形态端到端（阶段一原型）


def test_realworld_announcement_sample_end_to_end(api, auth, seeded):
    """巨潮风格公告摘要样例：公告标题进证据链、公告日期进时效、脏 uscc 进有效性候选。"""
    import os
    import sqlite3

    ingest = api.post(
        "/api/v1/ingest/runs",
        json={
            "connector": "csv",
            "params": {"path": "data/sample/真实公告风格示例.csv"},
        },
        headers=auth["admin"],
    )
    assert ingest.status_code == 200, ingest.text
    stats = ingest.json()["stats"]
    assert stats["entities_created"] == 4
    assert stats["statements_created"] == 4

    # 证据链回溯到公告标题（document_title 不再是 csv-fixture）
    db_path = os.environ["CG_DATABASE_URL"].split("///", 1)[1]
    conn = sqlite3.connect(db_path)
    try:
        sid = conn.execute("SELECT s.id FROM relationship_statements s LIMIT 1").fetchone()[0]
        titles = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT d.title FROM source_documents d JOIN source_snapshots sn "
                "ON sn.document_id = d.id"
            ).fetchall()
        ]
    finally:
        conn.close()
    assert any("年度报告" in t or "季度报告" in t for t in titles), "来源文档应携带公告标题"
    assert sid

    # 时效规则吃真实公告日期：公告约 1.4 年前发布，1 年阈值下应出现候选
    stale = api.get(
        "/api/v1/evidence/staleness", params={"years": 1}, headers=auth["viewer"]
    ).json()
    assert stale["stale_count"] >= 1

    # 质量有效性：样例的编造 uscc 校验位非法（真实形态脏数据演示）
    quality = api.get("/api/v1/evidence/quality", headers=auth["viewer"]).json()
    assert quality["validity"]["invalid_count"] >= 2
