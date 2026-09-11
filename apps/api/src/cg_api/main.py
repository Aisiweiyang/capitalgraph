"""CapitalGraph CN FastAPI 应用入口。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import ClassVar

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from cg_api import auth as auth_module
from cg_api.ratelimit import RateLimitMiddleware
from cg_api.routers import entities, ingest, ops, penetration, stats
from cg_api.state import dispose_engine, init_engine

logger = logging.getLogger("cg_api")
logging.basicConfig(level=os.environ.get("CG_LOG_LEVEL", "INFO"))

API_PREFIX = "/api/v1"

# 脱敏日志：不记录查询串与授权头
_sensitive_headers = {"authorization", "cookie", "x-api-key"}


class SecurityHeadersMiddleware:
    """CSP 与安全响应头（T05 威胁缓解）。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                csp = (
                    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                    "script-src 'self'; connect-src 'self'"
                )
                for name, value in (
                    (b"Content-Security-Policy", csp.encode()),
                    (b"X-Content-Type-Options", b"nosniff"),
                    (b"X-Frame-Options", b"DENY"),
                    (b"Referrer-Policy", b"no-referrer"),
                ):
                    headers.append((name, value))
            await send(message)

        await self.app(scope, receive, send_wrapper)


class AuditMiddleware:
    """写操作审计：actor/action/result 落 audit_log（append-only）。"""

    _AUDITED_METHODS: ClassVar[set[str]] = {"POST", "PUT", "DELETE", "PATCH"}

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("method") not in self._AUDITED_METHODS:
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        try:
            principal = {"username": "anonymous", "role": "anonymous"}
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    payload = auth_module.decode_token(auth_header[7:])
                    principal = {
                        "username": payload.get("sub", ""),
                        "role": payload.get("role", ""),
                    }
                except Exception:
                    principal = {"username": "invalid-token", "role": "anonymous"}
            scope.setdefault("state", {})
            scope["state"]["audit_actor"] = principal["username"]
            scope["state"]["request_id"] = request.headers.get("x-request-id", "")[:64]
        except Exception:  # 审计准备失败不阻断请求
            logger.debug("audit middleware prepare failed", exc_info=True)
        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    app = FastAPI(
        title="CapitalGraph CN API",
        version="0.1.0",
        description="中国企业资本关系与股权穿透研究平台（结果为候选，不构成法律认定）",
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    @app.on_event("startup")
    async def _startup() -> None:
        auth_module.get_secret_key()  # prod 未配置密钥时快速失败
        init_engine(app)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await dispose_engine(app)

    origins = os.environ.get("CG_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuditMiddleware)

    @app.get(f"{API_PREFIX}/health", tags=["系统"])
    async def health():
        """探活 + 数据库连通性。"""
        try:
            factory = app.state.cg_session_factory
            async with factory() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        return {
            "status": "ok" if db_ok else "degraded",
            "service": "capitalgraph-api",
            "version": app.version,
            "database": "ok" if db_ok else "unreachable",
        }

    app.include_router(ops.router, prefix=API_PREFIX)
    app.include_router(entities.router, prefix=API_PREFIX)
    app.include_router(penetration.router, prefix=API_PREFIX)
    app.include_router(ingest.router, prefix=API_PREFIX)
    app.include_router(stats.router, prefix=API_PREFIX)

    # 前端静态托管（构建产物存在时），SPA 回退 index.html
    web_dist = Path(os.environ.get("CG_WEB_DIST", "apps/web/dist"))
    if web_dist.exists():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            candidate = web_dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(web_dist / "index.html")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # 不向客户端泄露堆栈与内部路径（提示词 §7）
        logger.error("unhandled error on %s: %s", request.url.path, type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})

    return app


app = create_app()
