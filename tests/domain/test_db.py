"""db.py 与 normalization 的防御性分支补测（引擎构造不建连）。"""

from __future__ import annotations

import pytest
from cg_domain.db import default_database_url, make_engine
from cg_domain.normalization import is_valid_uscc, normalize_name


def test_normalize_empty_name_is_empty():
    assert normalize_name("") == ""
    assert normalize_name("   ") == "", "纯空白等价空名"


def test_uscc_with_illegal_charset_is_invalid():
    # 长度合法但含字符集外的字符（I/O/S/V/Z 不在 GB 32100-2015 集内）
    assert not is_valid_uscc("91350100M000100YIA")
    assert not is_valid_uscc("91350100M000100YSO")


def test_make_engine_non_sqlite_branch(monkeypatch):
    """非 sqlite URL 走通用 create_async_engine 分支（mock 掉驱动依赖，只验参数）。"""
    import cg_domain.db as dbmod

    captured: dict = {}

    def fake_create(url, *, echo, pool_pre_ping):
        captured.update(url=url, echo=echo, pool_pre_ping=pool_pre_ping)

    monkeypatch.setattr(dbmod, "create_async_engine", fake_create)
    dbmod.make_engine(
        "postgresql+asyncpg://cg:cg@localhost:5432/capitalgraph", echo=True
    )
    assert captured["url"] == "postgresql+asyncpg://cg:cg@localhost:5432/capitalgraph"
    assert captured["echo"] is True
    assert captured["pool_pre_ping"] is True, "非 sqlite 分支必须保留 pool_pre_ping"


def test_default_database_url_falls_back(monkeypatch):
    monkeypatch.delenv("CG_DATABASE_URL", raising=False)
    assert default_database_url() == "sqlite+aiosqlite:///./data/capitalgraph.sqlite3"
