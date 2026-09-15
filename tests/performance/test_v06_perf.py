"""v0.6 性能基线（切片 D）：2000 声明规模下 /evidence/coverage/timeline 与 /evidence/staleness。

- 仿 test_v05_perf.py：确定性合成（seed=42），规模以实际导入统计为准并随报告输出；
- 只记录与断言护栏（超时阈值），不伪造数字；实测值写入 TEST_REPORT.md v0.6；
- 覆盖率/时效均为全声明扫描型只读端点，护栏与 v0.5 同数量级（默认超时 10s 级别）。
"""

from __future__ import annotations

import os
import platform
import statistics
import time
from pathlib import Path

import pytest
from cg_api.main import create_app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.performance

os.environ.setdefault("CG_ENV", "test")


def _setup(tmp_path: Path, entities: str) -> tuple[TestClient, dict]:
    from argon2 import PasswordHasher
    from cg_domain.db import make_engine, make_session_factory
    from cg_domain.enums import Role
    from cg_domain.orm import Base, User

    db_path = tmp_path / "perf-v06.sqlite3"
    os.environ["CG_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    engine = make_engine(f"sqlite+aiosqlite:///{db_path}")
    import asyncio

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        hasher = PasswordHasher()
        factory = make_session_factory(engine)
        async with factory() as session:
            session.add(
                User(
                    username="admin",
                    password_hash=hasher.hash("admin-demo-password"),
                    role=Role.ADMIN.value,
                )
            )
            session.add(
                User(
                    username="viewer",
                    password_hash=hasher.hash("viewer-demo-password"),
                    role=Role.VIEWER.value,
                )
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(_create())
    client = TestClient(create_app())
    client.__enter__()

    def _login(username: str, password: str) -> dict:
        resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    admin_headers = _login("admin", "admin-demo-password")
    viewer_headers = _login("viewer", "viewer-demo-password")
    ingest = client.post(
        "/api/v1/ingest/runs",
        json={"connector": "synthetic", "params": {"seed": "42", "entities": entities}},
        headers=admin_headers,
    )
    assert ingest.status_code == 200, ingest.text
    stats = ingest.json()["stats"]
    return client, {"viewer_headers": viewer_headers, "stats": stats}


def _bench(fn, runs: int = 5) -> dict:
    durations = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        durations.append((time.perf_counter() - start) * 1000)
    return {
        "p50_ms": round(statistics.median(durations), 1),
        "max_ms": round(max(durations), 1),
        "runs": runs,
    }


def test_evidence_quality_endpoints_at_2000_statements(tmp_path: Path):
    client, meta = _setup(tmp_path, entities="640")
    try:
        statements = meta["stats"]["statements_created"]
        entities_total = meta["stats"]["entities_created"]
        info = {
            "machine": platform.machine(),
            "python": platform.python_version(),
            "system": platform.system(),
        }

        timeline_times = _bench(
            lambda: client.get("/api/v1/evidence/coverage/timeline", headers=meta["viewer_headers"])
        )
        timeline_resp = client.get(
            "/api/v1/evidence/coverage/timeline", headers=meta["viewer_headers"]
        )
        assert timeline_resp.status_code == 200
        timeline = timeline_resp.json()
        covered_years = len(timeline["timeline"])

        stale_times = _bench(
            lambda: client.get(
                "/api/v1/evidence/staleness",
                params={"years": 5},
                headers=meta["viewer_headers"],
            )
        )
        stale_resp = client.get(
            "/api/v1/evidence/staleness", params={"years": 5}, headers=meta["viewer_headers"]
        )
        assert stale_resp.status_code == 200
        stale_count = stale_resp.json()["stale_count"]

        print(
            f"\n[perf-v0.6] 环境: {info}\n"
            f"[perf-v0.6] 规模: entities={entities_total} statements={statements} "
            f"(目标 ≈2000) timeline 年度数={covered_years} 5 年阈值候选={stale_count}\n"
            f"[perf-v0.6] /evidence/coverage/timeline: {timeline_times}\n"
            f"[perf-v0.6] /evidence/staleness: {stale_times}"
        )
        # 护栏：与 v0.5 端点同数量级（默认超时 10s）；实际应远低于此
        assert timeline_times["max_ms"] < 10_000
        assert stale_times["max_ms"] < 10_000
        # 确定性断言：seed=42 下质押证据恒存在（2019-01-01 取证），趋势覆盖 ≥1 个年度
        assert covered_years >= 1
        assert stale_count >= 1
    finally:
        client.__exit__(None, None, None)
