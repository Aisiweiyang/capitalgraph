"""采集路由：运行 connector、查看运行历史。"""

from __future__ import annotations

from cg_connectors.base import ConnectorContext
from cg_connectors.ingest import run_connector
from cg_connectors.registry import get_connector, list_connectors
from cg_domain.config import load_settings
from fastapi import APIRouter, HTTPException, status

from cg_api.auth import AnalystUser, ViewerUser
from cg_api.deps import Ctx, DbSession, Repo
from cg_api.schemas import IngestRunIn, IngestRunOut

router = APIRouter(prefix="/ingest", tags=["采集"])


@router.get("/connectors")
async def connectors(_user: ViewerUser):
    return [
        {
            "connector_id": c.spec().connector_id,
            "description": c.spec().description,
            "allowed_use": c.spec().allowed_use,
            "license_name": c.spec().license_name,
            "rate_limit_per_sec": c.spec().rate_limit_per_sec,
        }
        for c in list_connectors()
    ]


@router.post("/runs", response_model=IngestRunOut)
async def start_run(
    body: IngestRunIn,
    db: DbSession,
    repo: Repo,
    user: AnalystUser,
    ctx: Ctx,
):
    connector = get_connector(body.connector)
    if connector is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"连接器不可用或已停用: {body.connector}")
    settings = load_settings()
    run_ctx = ConnectorContext(
        params=body.params,
        rate_limit_per_sec=settings.connector_rate_limit_per_sec,
        store_raw_documents=settings.store_raw_documents,
    )
    stats = await run_connector(db, connector, run_ctx)
    if stats is None:
        await repo.audit(
            actor=user["username"],
            action="ingest.skip_idempotent",
            target=body.connector,
            request_id=ctx.request_id,
            result="skipped",
        )
        return IngestRunOut(status="idempotent_hit", message="相同参数的运行已完成过，跳过")
    await repo.audit(
        actor=user["username"],
        action="ingest.run",
        target=body.connector,
        request_id=ctx.request_id,
        result="ok",
        detail=stats.to_dict(),
    )
    return IngestRunOut(status="succeeded", stats=stats.to_dict())
