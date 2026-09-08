"""请求级依赖：数据库会话与请求上下文。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from cg_domain.repo import Repository
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from cg_api.state import get_session_factory, init_engine


@dataclass
class RequestContext:
    request_id: str
    actor: str = "anonymous"

    def audit_detail(self) -> dict:
        return {"request_id": self.request_id}


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    try:
        factory = get_session_factory(request.app)
    except AttributeError:
        # lifespan 未跑（如部分测试客户端）时的惰性初始化
        factory = init_engine(request.app)[1]
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_repo(session: Annotated[AsyncSession, Depends(get_db_session)]) -> Repository:
    return Repository(session)


async def get_request_context(request: Request) -> RequestContext:
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    return RequestContext(request_id=request_id)


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
Repo = Annotated[Repository, Depends(get_repo)]
Ctx = Annotated[RequestContext, Depends(get_request_context)]
