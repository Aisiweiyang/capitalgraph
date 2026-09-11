"""总览统计路由：为仪表板提供只读聚合，全部为发布层数据，可随时重算。"""

from __future__ import annotations

from cg_domain.orm import (
    Entity,
    IngestionRun,
    ReviewItem,
    SourceDocument,
    SourceSnapshot,
    Statement,
)
from fastapi import APIRouter
from sqlalchemy import String, func, select

from cg_api.auth import ViewerUser
from cg_api.deps import Repo

router = APIRouter(tags=["统计"])

# Date 列在 SQLite/PostgreSQL 下 cast 为字符串后均为 ISO "YYYY-MM-DD"，取前 4 位即年份
_year = func.substr(func.cast(Statement.valid_from, String), 1, 4)


@router.get("/stats")
async def overview_stats(repo: Repo, _user: ViewerUser):
    """实体、声明、来源、复核与采集任务的总量与分布聚合。

    只做计数与分组，不输出任何主体明细，viewer 角色即可访问。
    """
    s = repo.session

    entities_total = (await s.execute(select(func.count(Entity.id)))).scalar_one()
    kind_rows = await s.execute(select(Entity.kind, func.count()).group_by(Entity.kind))
    entities_by_kind = {kind: int(n) for kind, n in kind_rows.all()}

    statements_total = (await s.execute(select(func.count(Statement.id)))).scalar_one()
    predicate_rows = await s.execute(
        select(Statement.predicate, func.count()).group_by(Statement.predicate)
    )
    statements_by_predicate = {p: int(n) for p, n in predicate_rows.all()}
    status_rows = await s.execute(select(Statement.status, func.count()).group_by(Statement.status))
    statements_by_status = {st: int(n) for st, n in status_rows.all()}
    year_rows = await s.execute(select(_year, func.count()).group_by(_year).order_by(_year))
    statements_by_year = {str(y): int(n) for y, n in year_rows.all()}

    sources_total = (await s.execute(select(func.count(SourceDocument.id)))).scalar_one()
    snapshots_total = (await s.execute(select(func.count(SourceSnapshot.id)))).scalar_one()

    review_open = (
        await s.execute(select(func.count(ReviewItem.id)).where(ReviewItem.status == "open"))
    ).scalar_one()

    runs_total = (await s.execute(select(func.count(IngestionRun.id)))).scalar_one()
    runs_failed = (
        await s.execute(select(func.count(IngestionRun.id)).where(IngestionRun.status == "failed"))
    ).scalar_one()
    last_run = (
        await s.execute(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(1))
    ).scalar_one_or_none()

    return {
        "entities_total": int(entities_total),
        "entities_by_kind": entities_by_kind,
        "statements_total": int(statements_total),
        "statements_by_predicate": statements_by_predicate,
        "statements_by_status": statements_by_status,
        "statements_by_year": statements_by_year,
        "sources_total": int(sources_total),
        "snapshots_total": int(snapshots_total),
        "review_open": int(review_open),
        "runs_total": int(runs_total),
        "runs_failed": int(runs_failed),
        "last_run": (
            {
                "connector_id": last_run.connector_id,
                "status": last_run.status,
                "started_at": str(last_run.started_at),
                "finished_at": str(last_run.finished_at) if last_run.finished_at else None,
            }
            if last_run
            else None
        ),
    }
