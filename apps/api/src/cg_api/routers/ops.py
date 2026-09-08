"""运营路由：认证、复核队列、质量、审计、用户管理。"""

from __future__ import annotations

import json

from cg_domain.enums import Role
from cg_domain.orm import Entity, User
from fastapi import APIRouter, HTTPException, status

from cg_api.auth import (
    AdminUser,
    AnalystUser,
    ViewerUser,
    hash_password,
    issue_token,
    verify_password,
)
from cg_api.deps import Ctx, DbSession, Repo
from cg_api.schemas import LoginIn, LoginOut, ReviewResolveIn, UserCreateIn

router = APIRouter(tags=["运营"])


# ---------------------------------------------------------------- 认证


@router.post("/auth/login", response_model=LoginOut)
async def login(body: LoginIn, db: DbSession, repo: Repo, ctx: Ctx):
    user = await repo.get_user_by_username(body.username)
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        await repo.audit(
            actor=body.username[:64],
            action="auth.login",
            request_id=ctx.request_id,
            result="denied",
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或口令错误")
    token = issue_token(user)
    await repo.audit(
        actor=user.username, action="auth.login", request_id=ctx.request_id, result="ok"
    )
    return LoginOut(access_token=token, role=user.role, username=user.username)


# ---------------------------------------------------------------- 复核与质量


@router.get("/review/items")
async def review_items(repo: Repo, _user: ViewerUser, status_filter: str | None = None):
    rows = await repo.list_review_items(status=status_filter)
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "payload": json.loads(r.payload_json or "{}"),
            "status": r.status,
            "assignee": r.assignee,
            "created_at": str(r.created_at),
        }
        for r in rows
    ]


@router.post("/review/items/{item_id}/resolve")
async def resolve_review(
    item_id: str,
    body: ReviewResolveIn,
    repo: Repo,
    user: AnalystUser,
    ctx: Ctx,
):
    item = await repo.resolve_review_item(item_id, body.note, user["username"])
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "复核项不存在")
    await repo.audit(
        actor=user["username"],
        action="review.resolve",
        target=item_id,
        request_id=ctx.request_id,
        result="ok",
        detail={"note": body.note[:200]},
    )
    return {"id": item.id, "status": item.status}


@router.get("/quality/issues")
async def quality_issues(repo: Repo, _user: ViewerUser):
    from cg_domain.orm import QualityIssue
    from sqlalchemy import select

    rows = (
        (
            await repo.session.execute(
                select(QualityIssue).order_by(QualityIssue.detected_at.desc()).limit(200)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "rule_name": r.rule_name,
            "severity": r.severity,
            "entity_id": r.entity_id,
            "statement_id": r.statement_id,
            "detail": json.loads(r.detail_json or "{}"),
            "status": r.status,
        }
        for r in rows
    ]


# ---------------------------------------------------------------- 审计与用户管理（admin）


@router.get("/audit")
async def audit_log(repo: Repo, _user: AdminUser, limit: int = 100):
    rows = await repo.audit_tail(limit=min(limit, 500))
    return [
        {
            "id": r.id,
            "at": str(r.at),
            "actor": r.actor,
            "action": r.action,
            "target": r.target,
            "request_id": r.request_id,
            "result": r.result,
            "detail": json.loads(r.detail_json or "{}"),
        }
        for r in rows
    ]


@router.post("/admin/users")
async def create_user(body: UserCreateIn, db: DbSession, repo: Repo, user: AdminUser, ctx: Ctx):
    if body.role not in {r.value for r in Role}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "角色非法")
    if len(body.password) < 8:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "口令至少 8 位")
    existing = await repo.get_user_by_username(body.username)
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在")
    created = await repo.create_user(body.username, hash_password(body.password), Role(body.role))
    await repo.audit(
        actor=user["username"],
        action="admin.user_create",
        target=created.username,
        request_id=ctx.request_id,
        result="ok",
        detail={"role": created.role},
    )
    return {"id": created.id, "username": created.username, "role": created.role}


@router.get("/admin/summary")
async def admin_summary(repo: Repo, _user: AdminUser):
    from cg_domain.orm import Statement
    from sqlalchemy import func, select

    entity_count = (await repo.session.execute(select(func.count(Entity.id)))).scalar_one()
    statement_count = (await repo.session.execute(select(func.count(Statement.id)))).scalar_one()
    user_count = (await repo.session.execute(select(func.count(User.id)))).scalar_one()
    return {
        "entities": int(entity_count),
        "statements": int(statement_count),
        "users": int(user_count),
    }
