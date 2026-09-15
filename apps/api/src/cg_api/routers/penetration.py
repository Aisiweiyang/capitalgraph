"""穿透路由：向上/向下穿透、聚合、UBO 候选、CSV 导出。"""

from __future__ import annotations

import csv
import io
from datetime import date

from cg_capital_graph import (
    GraphEdge,
    PenetrationTimeoutError,
    analyse,
    penetrate,
    result_to_jsonable,
)
from cg_domain.config import load_settings
from cg_domain.models import PenetrationConfig
from cg_domain.orm import Entity
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from cg_api.auth import ViewerUser
from cg_api.deps import Repo

router = APIRouter(prefix="/penetration", tags=["穿透"])

# 服务端硬上限：拒绝放宽超过护栏的请求（立项硬约束）
_HARD_LIMITS = {"max_depth": 12, "max_paths": 100000, "max_nodes": 1000000, "timeout_seconds": 60.0}


async def _build_edges(repo, at: date | None) -> list[GraphEdge]:
    rows = await repo.effective_edges(at)
    return [
        GraphEdge(
            statement_id=r.statement_id,
            subject=r.subject_id,
            obj=r.object_id,
            predicate=r.predicate,
            share_scaled=r.share_ratio_scaled,
            voting_scaled=r.voting_ratio_scaled,
        )
        for r in rows
    ]


async def _kinds_and_names(repo, entity_ids: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    from sqlalchemy import select

    if not entity_ids:
        return {}, {}
    rows = await repo.session.execute(
        select(Entity.id, Entity.primary_name, Entity.kind).where(Entity.id.in_(set(entity_ids)))
    )
    names, kinds = {}, {}
    for eid, name, kind in rows.all():
        names[eid] = name
        kinds[eid] = kind
    return kinds, names


@router.get("/{entity_id}")
async def penetration(
    repo: Repo,
    _user: ViewerUser,
    entity_id: str,
    at: date | None = None,
    direction: str = Query(default="up", pattern="^(up|down)$"),
    max_depth: int | None = Query(default=None, ge=1, le=12),
    min_ratio_percent: float | None = Query(default=None, ge=0.0, le=100.0),
):
    entity = await repo.get(entity_id)
    if entity is None:
        raise HTTPException(404, "实体不存在")
    defaults = load_settings().penetration
    config = PenetrationConfig(
        at=at,
        direction="up" if direction == "up" else "down",
        max_depth=max_depth if max_depth is not None else defaults.max_depth,
        min_ratio_percent=(
            min_ratio_percent if min_ratio_percent is not None else defaults.min_ratio * 100
        ),
        max_paths=defaults.max_paths,
        max_nodes=defaults.max_nodes,
        timeout_seconds=defaults.timeout_seconds,
    )
    edges = await _build_edges(repo, at)
    kinds, names = await _kinds_and_names(repo, [e.subject for e in edges] + [e.obj for e in edges])
    try:
        result = penetrate(entity_id, edges, config)
    except PenetrationTimeoutError:
        raise HTTPException(422, "穿透计算超时：请缩小深度或提高比例阈值") from None
    report = analyse(entity_id, result, edges, config, entity_kind=kinds)
    payload = result_to_jsonable(report, result, entity_kind=kinds)
    # 逐边比例（图上标注用）：statement_id → 百分数
    ratio_by_statement = {
        e.statement_id: (
            round(e.share_scaled * 100.0 / 10**8, 6) if e.share_scaled is not None else None
        )
        for e in edges
    }
    for path in payload["paths"] + payload["control_paths"]:
        path["edge_ratios"] = [ratio_by_statement.get(sid) for sid in path["statement_ids"]]
    payload["entity_name"] = names.get(entity_id, entity.primary_name)
    payload["names"] = names
    payload["at"] = str(at) if at else None
    payload["config"] = {
        "max_depth": config.max_depth,
        "min_ratio_percent": config.min_ratio_percent,
        "max_paths": config.max_paths,
        "max_nodes": config.max_nodes,
        "timeout_seconds": config.timeout_seconds,
    }
    return payload


@router.get("/{entity_id}/export.csv")
async def export_csv(
    repo: Repo,
    _user: ViewerUser,
    entity_id: str,
    at: date | None = None,
    direction: str = Query(default="up", pattern="^(up|down)$"),
):
    """聚合结果 CSV 导出（UTF-8 BOM + 公式注入转义）。"""
    payload = await penetration(
        repo, _user, entity_id, at=at, direction=direction, max_depth=None, min_ratio_percent=None
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "股东ID",
            "股东名称",
            "主体类型",
            "有效权益(%)",
            "直接持股(%)",
            "路径数",
            "比例缺失",
            "声明ID",
        ]
    )
    for agg in payload["aggregates"]:
        writer.writerow(
            [
                _escape_csv_cell(agg["entity_id"]),
                _escape_csv_cell(payload["names"].get(agg["entity_id"], "")),
                _escape_csv_cell(agg.get("entity_kind") or ""),
                agg["effective_percent"] if agg["effective_percent"] is not None else "",
                agg["direct_percent"] if agg["direct_percent"] is not None else "",
                agg["path_count"],
                "是" if agg["unknown_ratio"] else "否",
                " ".join(agg["statement_ids"]),
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter(["\ufeff", buffer.read()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="penetration_{entity_id[:8]}.csv"'},
    )


def _escape_csv_cell(value: str) -> str:
    """公式注入防护：以 = + - @ 开头的单元格加前缀单引号。"""
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
        return "'" + value
    return value
