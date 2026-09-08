"""应用级状态：引擎/会话工厂/设置的进程内单例。"""

from __future__ import annotations

from cg_domain.config import Settings, load_settings
from cg_domain.db import make_engine, make_session_factory
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def init_engine(app) -> tuple[AsyncEngine, async_sessionmaker]:
    settings: Settings = load_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    app.state.cg_settings = settings
    app.state.cg_engine = engine
    app.state.cg_session_factory = factory
    return engine, factory


async def dispose_engine(app) -> None:
    engine = getattr(app.state, "cg_engine", None)
    if engine is not None:
        await engine.dispose()


def get_session_factory(app) -> async_sessionmaker:
    return app.state.cg_session_factory
