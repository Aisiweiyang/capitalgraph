"""v0.5 性能基线（切片 D）：2000 声明规模下 /events 与 /families/compare 响应时间。

- 数据为确定性合成（seed=42），规模以实际导入统计为准并随报告输出；
- 只记录与断言护栏（超时阈值），不伪造数字；实测值写入 TEST_REPORT.md v0.5；
- 超过阈值只记录并在已知限制说明，不阻塞交付口径：此处断言上限为穿透护栏
  默认超时（10s）级别，若未来超阈值应先查回归再评估口径。
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

_WINDOW = {"from": "2020-01-01", "to": "2024-01-01"}


def _setup(tmp_path: Path, entities: str) -> tuple[TestClient, dict]:
    from argon2 import PasswordHasher
    from cg_domain.db import make_engine, make_session_factory
    from cg_domain.enums import Role
    from cg_domain.orm import Base, User

    db_path = tmp_path / "perf-v05.sqlite3"
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
            await session.commit()
        await engine.dispose()

    asyncio.run(_create())
    client = TestClient(create_app())
    client.__enter__()
    resp = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin-demo-password"}
    )
    assert resp.status_code == 200
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    ingest = client.post(
        "/api/v1/ingest/runs",
        json={"connector": "synthetic", "params": {"seed": "42", "entities": entities}},
        headers=headers,
    )
    assert ingest.status_code == 200, ingest.text
    stats = ingest.json()["stats"]
    return client, {"headers": headers, "stats": stats}


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


def test_events_and_families_compare_at_2000_statements(tmp_path: Path):
    client, meta = _setup(tmp_path, entities="640")
    try:
        statements = meta["stats"]["statements_created"]
        entities_total = meta["stats"]["entities_created"]
        info = {
            "machine": platform.machine(),
            "python": platform.python_version(),
            "system": platform.system(),
        }

        events_times = _bench(
            lambda: client.get("/api/v1/events", params=_WINDOW, headers=meta["headers"])
        )
        events_resp = client.get("/api/v1/events", params=_WINDOW, headers=meta["headers"])
        assert events_resp.status_code == 200
        events_total = events_resp.json()["total"]

        compare_times = _bench(
            lambda: client.get("/api/v1/families/compare", params=_WINDOW, headers=meta["headers"])
        )
        compare_resp = client.get(
            "/api/v1/families/compare", params=_WINDOW, headers=meta["headers"]
        )
        assert compare_resp.status_code == 200
        flows_times = _bench(
            lambda: client.get("/api/v1/flows/compare", params=_WINDOW, headers=meta["headers"])
        )
        assert (
            client.get("/api/v1/flows/compare", params=_WINDOW, headers=meta["headers"]).status_code
            == 200
        )

        print(
            f"\n[perf-v0.5] 环境: {info}\n"
            f"[perf-v0.5] 规模: entities={entities_total} statements={statements} "
            f"(目标 ≈2000)\n"
            f"[perf-v0.5] /events（窗口 {events_total} 事件）: {events_times}\n"
            f"[perf-v0.5] /families/compare: {compare_times}\n"
            f"[perf-v0.5] /flows/compare: {flows_times}"
        )
        # 护栏：与穿透护栏同数量级（默认超时 10s）；实际应远低于此
        assert events_times["max_ms"] < 10_000
        assert compare_times["max_ms"] < 10_000
        assert flows_times["max_ms"] < 10_000
        # 事件流在合成数据上的确定性窗口内应有事件（2018 基线 + 2022 转移）
        assert events_total >= 2
    finally:
        client.__exit__(None, None, None)
