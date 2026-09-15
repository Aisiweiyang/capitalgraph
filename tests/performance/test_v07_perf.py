"""v0.7 性能基线（切片 D）：2000 声明规模下 /evidence/quality 质量总览端点。

- 仿 test_v06_perf.py：确定性合成（seed=42），只记录与断言护栏（超时阈值），
  实测值写入 TEST_REPORT.md v0.7；
- /evidence/quality 内部为四次只读扫描（覆盖率 / 时效 / 声明键 / 标识符），
  护栏与既有质量端点同数量级（默认超时 10s 级别）。
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

    db_path = tmp_path / "perf-v07.sqlite3"
    os.environ["CG_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    engine = make_engine(f"sqlite+aiosqlite:///{db_path}")
    import asyncio

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        hasher = PasswordHasher()
        factory = make_session_factory(engine)
        async with factory() as session:
            for username, role in (
                ("admin", Role.ADMIN),
                ("viewer", Role.VIEWER),
            ):
                session.add(
                    User(
                        username=username,
                        password_hash=hasher.hash(f"{username}-demo-password"),
                        role=role.value,
                    )
                )
            await session.commit()
        await engine.dispose()

    asyncio.run(_create())
    client = TestClient(create_app())
    client.__enter__()

    def _login(username: str) -> dict:
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": f"{username}-demo-password"},
        )
        assert resp.status_code == 200
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    admin_headers = _login("admin")
    viewer_headers = _login("viewer")
    ingest = client.post(
        "/api/v1/ingest/runs",
        json={"connector": "synthetic", "params": {"seed": "42", "entities": entities}},
        headers=admin_headers,
    )
    assert ingest.status_code == 200, ingest.text
    return client, {"admin_headers": admin_headers, "viewer_headers": viewer_headers}


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


def test_quality_overview_at_2000_statements(tmp_path: Path):
    client, meta = _setup(tmp_path, entities="640")
    try:
        info = {
            "machine": platform.machine(),
            "python": platform.python_version(),
            "system": platform.system(),
        }

        quality_times = _bench(
            lambda: client.get(
                "/api/v1/evidence/quality", params={"years": 5}, headers=meta["viewer_headers"]
            )
        )
        resp = client.get(
            "/api/v1/evidence/quality", params={"years": 5}, headers=meta["viewer_headers"]
        )
        assert resp.status_code == 200
        body = resp.json()

        # RBAC 护栏：写通道之外的只读端点对 viewer 开放，匿名拒绝
        assert client.get("/api/v1/evidence/quality").status_code == 401

        print(
            f"\n[perf-v0.7] 环境: {info}\n"
            f"[perf-v0.7] /evidence/quality（五维度总览）: {quality_times}\n"
            f"[perf-v0.7] counts: {body['counts']}"
        )
        # 护栏：内部四次扫描，放宽到两倍护栏仍远低于默认超时
        assert quality_times["max_ms"] < 20_000
        # 确定性：合成库已知候选（质押时效 2019-01-01）
        assert body["counts"]["staleness"] >= 1
    finally:
        client.__exit__(None, None, None)
