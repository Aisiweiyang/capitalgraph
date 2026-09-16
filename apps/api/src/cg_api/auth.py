"""认证与 RBAC。

- 口令：argon2id 哈希（不存明文，不可逆）。
- 令牌：HS256 JWT，密钥只来自环境 CG_SECRET_KEY；生产未配置则拒绝启动。
- 授权：路由声明所需最低角色，依赖注入层强制（默认拒绝），前端隐藏不是安全边界。
"""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cg_domain.enums import Role
from cg_domain.orm import User
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# 成本参数可经环境变量覆盖（默认与 argon2-cffi 库默认一致）；测试套件用低档位换速度，
# 校验不受影响：argon2 编码串自带参数，verify 按哈希串内的参数执行
_hasher = PasswordHasher(
    time_cost=int(os.environ.get("CG_ARGON2_TIME_COST", "3")),
    memory_cost=int(os.environ.get("CG_ARGON2_MEMORY_COST", str(64 * 1024))),
    parallelism=int(os.environ.get("CG_ARGON2_PARALLELISM", "4")),
)
_bearer = HTTPBearer(auto_error=False)

_ROLE_RANK = {Role.VIEWER: 1, Role.ANALYST: 2, Role.ADMIN: 3}


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


_dev_ephemeral_secret: str | None = None


def get_secret_key(*, for_startup: bool = False) -> str:
    """生产（CG_ENV=prod）必须有密钥；开发未配置时用进程级随机值并提示。

    进程内只生成一次：保证同一进程内签发与校验使用同一密钥。
    """
    global _dev_ephemeral_secret
    secret = os.environ.get("CG_SECRET_KEY", "").strip()
    if secret:
        return secret
    if os.environ.get("CG_ENV", "dev") == "prod" or for_startup:
        raise RuntimeError("生产环境必须设置 CG_SECRET_KEY 环境变量")
    if _dev_ephemeral_secret is None:
        _dev_ephemeral_secret = secrets.token_hex(32)  # dev 临时密钥：重启失效，仅本地演示可用
    return _dev_ephemeral_secret


def issue_token(user: User, *, minutes: int | None = None) -> str:
    ttl = minutes if minutes is not None else int(os.environ.get("CG_ACCESS_TOKEN_MINUTES", "120"))
    now = datetime.now(UTC)
    payload = {
        "sub": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, get_secret_key(), algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_secret_key(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效令牌") from exc


async def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    """解析并注入当前主体 {username, role}。未携带令牌 → anonymous。"""
    if credentials is None or not credentials.credentials:
        return {"username": "anonymous", "role": "anonymous"}
    payload = decode_token(credentials.credentials)
    role = payload.get("role", "")
    if role not in _ROLE_RANK:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "未知角色")
    return {"username": str(payload.get("sub", "")), "role": role}


def require_role(minimum: Role):
    """路由级授权依赖。角色等级不足 → 403；匿名访问受限路由 → 401。"""

    async def checker(principal: Annotated[dict, Depends(current_principal)]) -> dict:
        role = principal.get("role", "anonymous")
        if role == "anonymous":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "请先登录")
        if _ROLE_RANK.get(Role(role), 0) < _ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足")
        return principal

    return checker


AdminUser = Annotated[dict, Depends(require_role(Role.ADMIN))]
AnalystUser = Annotated[dict, Depends(require_role(Role.ANALYST))]
ViewerUser = Annotated[dict, Depends(require_role(Role.VIEWER))]
