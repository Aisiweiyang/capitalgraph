"""仓储门面：一次会话内组合实体/声明/运营三组操作。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from cg_domain.repo.entities import EntityRepository
from cg_domain.repo.ops import OpsRepository
from cg_domain.repo.statements import EdgeRow, FlowRow, StatementRepository

__all__ = [
    "EdgeRow",
    "EntityRepository",
    "FlowRow",
    "OpsRepository",
    "Repository",
    "StatementRepository",
]


class Repository(EntityRepository, StatementRepository, OpsRepository):
    """聚合仓储。方法冲突时实体 > 声明 > 运营（当前无冲突）。"""

    def __init__(self, session: AsyncSession) -> None:
        EntityRepository.__init__(self, session)
        StatementRepository.__init__(self, session)
        OpsRepository.__init__(self, session)
