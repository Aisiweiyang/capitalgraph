"""数据库引擎与会话工厂（async）。SQLite 与 PostgreSQL 共用同一套代码路径。"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """从 URL 创建异步引擎。

    SQLite URL 指向文件时自动确保父目录存在；连接层允许同线程多连接复用
    （aiosqlite 默认检查线程，测试中跨事件循环复用引擎需要禁用）。
    """
    if database_url.startswith("sqlite"):
        _, _, path_part = database_url.partition("///")
        if path_part and path_part != ":memory:":
            Path(path_part).parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(
            database_url,
            echo=echo,
            connect_args={"check_same_thread": False} if "aiosqlite" in database_url else {},
        )

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragma(dbapi_conn, _record) -> None:
            """WAL：读写不互斥（并发读不再锁库，且为库文件持久属性）；
            busy_timeout：写竞争时等待而非立即报错。aiosqlite 同步适配层 execute 即执行。"""
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        return engine
    return create_async_engine(database_url, echo=echo, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def default_database_url() -> str:
    return os.environ.get("CG_DATABASE_URL", "sqlite+aiosqlite:///./data/capitalgraph.sqlite3")
