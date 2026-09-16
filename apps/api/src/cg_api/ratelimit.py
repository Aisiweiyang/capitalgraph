"""限流中间件：内存令牌桶（按 IP + 全局路由桶）。

单实例部署假设：多实例部署需换 Redis 后端（记录于 DELIVERY 已知限制）。
"""

from __future__ import annotations

import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class TokenBucket:
    def __init__(self, capacity: int, refill_per_sec: float) -> None:
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_per_sec = refill_per_sec
        self.updated = time.monotonic()

    def take(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.updated
        self.updated = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """按客户端 IP 限流。/health 不限流（供探活）。"""

    def __init__(self, app, per_minute: int | None = None) -> None:
        super().__init__(app)
        per_minute = per_minute or int(os.environ.get("CG_RATE_LIMIT_PER_MINUTE", "120"))
        self.bucket_capacity = per_minute
        self.refill = per_minute / 60.0
        self.buckets: dict[str, TokenBucket] = {}
        # 仅在可信反向代理之后才允许开启：XFF 可被客户端伪造，直连暴露时
        # 信任它等于限流可被任意绕过（默认关闭）
        self.trust_proxy = os.environ.get("CG_TRUST_PROXY", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }

    def _client_key(self, request: Request) -> str:
        if self.trust_proxy:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.endswith("/health") or request.method == "OPTIONS":
            return await call_next(request)
        key = self._client_key(request)
        bucket = self.buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self.bucket_capacity, self.refill)
            self.buckets[key] = bucket
            if len(self.buckets) > 10000:  # 防内存膨胀：淘汰最旧条目
                self.buckets.pop(next(iter(self.buckets)))
        if not bucket.take():
            retry_after = max(1, int(1 / self.refill))
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
