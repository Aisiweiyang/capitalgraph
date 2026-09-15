"""种子数据：演示用户 + 合成数据集。幂等（重复执行不重复创建）。"""

from __future__ import annotations

import argparse
import asyncio
import os

from cg_connectors.base import ConnectorContext
from cg_connectors.ingest import run_connector
from cg_connectors.synthetic import SyntheticConnector
from cg_domain.db import make_session_factory
from cg_domain.enums import Role
from cg_domain.repo import Repository

from cg_api.auth import hash_password

DEMO_USERS = [
    ("admin", "admin-demo-password", Role.ADMIN),
    ("analyst", "analyst-demo-password", Role.ANALYST),
    ("viewer", "viewer-demo-password", Role.VIEWER),
]


async def seed(
    database_url: str | None = None, *, entities: int = 40, seed_value: str = "42"
) -> dict:
    # 显式参数优先于环境变量；两者都缺省才落到默认库
    os.environ["CG_DATABASE_URL"] = database_url or os.environ.get(
        "CG_DATABASE_URL", "sqlite+aiosqlite:///./data/capitalgraph.sqlite3"
    )
    from cg_domain.db import make_engine

    engine = make_engine(os.environ["CG_DATABASE_URL"])

    from cg_domain.orm import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = make_session_factory(engine)

    result: dict = {"users": 0, "entities": 0, "statements": 0}
    async with factory() as session:
        repo = Repository(session)
        for username, password, role in DEMO_USERS:
            if await repo.get_user_by_username(username) is None:
                await repo.create_user(username, hash_password(password), role)
                result["users"] += 1
        connector = SyntheticConnector()
        ctx = ConnectorContext(params={"seed": seed_value, "entities": str(entities)})
        stats = await run_connector(session, connector, ctx)
        if stats:
            result["entities"] = stats.entities_created
            result["statements"] = stats.statements_created
        await session.commit()
    await engine.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="CapitalGraph CN 种子数据")
    parser.add_argument("--entities", type=int, default=40, help="合成主体数量")
    parser.add_argument("--seed", type=str, default="42", help="随机种子（保证可复现）")
    args = parser.parse_args()
    result = asyncio.run(seed(entities=args.entities, seed_value=args.seed))
    print(
        f"种子完成：新增用户 {result['users']}，实体 {result['entities']}，"
        f"声明 {result['statements']}（重复执行自动跳过已有数据）"
    )


if __name__ == "__main__":
    main()
