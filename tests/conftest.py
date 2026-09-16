"""pytest 公共夹具：内存 SQLite + 建表 + 会话。"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

# argon2 低档位：口令哈希在单测里被大量调用（每文件建用户+登录），默认档位拖慢套件；
# 必须在 cg_api.auth 模块导入前设置（模块级 PasswordHasher 读取一次）
os.environ.setdefault("CG_ARGON2_TIME_COST", "1")
os.environ.setdefault("CG_ARGON2_MEMORY_COST", "8192")
os.environ.setdefault("CG_ARGON2_PARALLELISM", "1")

import pytest
from cg_domain.orm import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture()
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()
