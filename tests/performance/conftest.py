"""性能测试共享夹具：一次建库（seed=42，640 实体 ≈ 2008 声明），全部性能用例复用。

此前三个性能用例各自重复建库 + 导入（约 36s/次）；数据同源（同 seed 同规模），
合并为会话级夹具后整段只付一次成本。
"""

from __future__ import annotations

import asyncio
import os
import platform
import statistics
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CG_ENV", "test")


@pytest.fixture(scope="session")
def perf_env(tmp_path_factory) -> Iterator[dict]:
    from argon2 import PasswordHasher
    from cg_api.main import create_app
    from cg_domain.db import make_engine, make_session_factory
    from cg_domain.enums import Role
    from cg_domain.orm import Base, User

    db_path: Path = tmp_path_factory.mktemp("perf") / "perf-shared.sqlite3"
    os.environ["CG_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    engine = make_engine(f"sqlite+aiosqlite:///{db_path}")

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        hasher = PasswordHasher()
        factory = make_session_factory(engine)
        async with factory() as session:
            for username, role in (("admin", Role.ADMIN), ("viewer", Role.VIEWER)):
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
    with client:

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
            json={"connector": "synthetic", "params": {"seed": "42", "entities": "640"}},
            headers=admin_headers,
        )
        assert ingest.status_code == 200, ingest.text
        yield {
            "client": client,
            "admin_headers": admin_headers,
            "viewer_headers": viewer_headers,
            "stats": ingest.json()["stats"],
            "info": {
                "machine": platform.machine(),
                "python": platform.python_version(),
                "system": platform.system(),
            },
        }


def bench(fn, runs: int = 5) -> dict:
    """同端点重复调用取 p50/max（共享工具，随用例输出到 TEST_REPORT）。"""
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
