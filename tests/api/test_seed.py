"""种子模块单测：幂等性 + 显式 database_url 优先于环境变量。"""

from __future__ import annotations

from pathlib import Path

import pytest
from cg_api.seed import seed

pytestmark = pytest.mark.asyncio


def _row_counts(db_path: Path) -> tuple[int, int, int]:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        statements = conn.execute("SELECT COUNT(*) FROM relationship_statements").fetchone()[0]
    finally:
        conn.close()
    return users, entities, statements


async def test_seed_is_idempotent(tmp_path: Path):
    db = tmp_path / "seed.sqlite3"
    url = f"sqlite+aiosqlite:///{db}"
    first = await seed(url, entities=10, seed_value="42")
    counts = _row_counts(db)
    assert first["users"] == 3
    assert first["entities"] == counts[1] > 0
    assert first["statements"] == counts[2] > 0

    second = await seed(url, entities=10, seed_value="42")
    assert second == {"users": 0, "entities": 0, "statements": 0}
    assert _row_counts(db) == counts, "重复种子不得改变行数"


async def test_seed_explicit_url_overrides_environment(tmp_path: Path, monkeypatch):
    """环境变量里已有 CG_DATABASE_URL 时，显式传入的 database_url 必须生效。"""
    decoy = tmp_path / "decoy.sqlite3"
    target = tmp_path / "target.sqlite3"
    monkeypatch.setenv("CG_DATABASE_URL", f"sqlite+aiosqlite:///{decoy}")

    result = await seed(f"sqlite+aiosqlite:///{target}", entities=5, seed_value="42")
    assert result["entities"] > 0
    assert target.exists(), "数据应落在显式指定的库"
    assert not decoy.exists(), "环境变量指向的库不应被写入"
