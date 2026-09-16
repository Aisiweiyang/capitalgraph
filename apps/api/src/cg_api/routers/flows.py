"""资本流动路由：省际流动、区域汇总、行业流向、年度趋势（只读聚合）。"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from cg_capital_graph import (
    FlowEdge,
    aggregate_flows,
    compare_flows,
    detect_cycles,
    flow_timeline,
    industry_flows,
    region_summary,
)
from cg_capital_graph.engine import GraphEdge
from cg_domain.orm import Entity
from cg_domain.repo import FlowRow
from fastapi import APIRouter, Query
from sqlalchemy import select

from cg_api.auth import ViewerUser
from cg_api.deps import Repo

router = APIRouter(tags=["资本流动"])

# 流动口径：资本放置类关系。controls 是治理关系，不计入资本流动（ADR-014）。
_FLOW_PREDICATES: tuple[str, ...] = ("holds_shares", "invests_in")


async def _load_flow_edges(repo: Repo, at: date | None) -> tuple[list[FlowEdge], list[FlowEdge]]:
    """返回 (跨省边, 全部有效边)。region 未知的主体的边只丢弃并计数，不猜测归属。"""
    rows = await repo.flow_rows(at, predicates=_FLOW_PREDICATES)
    region_by_entity: dict[str, str | None] = {
        row[0]: row[1]
        for row in (await repo.session.execute(select(Entity.id, Entity.region_code))).all()
    }
    all_edges: list[FlowEdge] = []
    for r in rows:
        src = region_by_entity.get(r.subject_id)
        dst = region_by_entity.get(r.object_id)
        if not src or not dst:
            continue
        all_edges.append(
            FlowEdge(
                statement_id=r.statement_id,
                from_region=src,
                to_region=dst,
                object_id=r.object_id,
                ratio_scaled=r.share_ratio_scaled,
                amount_scaled=r.amount_scaled,
                year=r.valid_from.year,
            )
        )
    return [e for e in all_edges if e.from_region != e.to_region], all_edges


async def _industry_pairs(repo: Repo, edges: list[FlowEdge]) -> list[tuple[FlowEdge, str | None]]:
    industry_by_entity: dict[str, str | None] = {
        row[0]: row[1]
        for row in (await repo.session.execute(select(Entity.id, Entity.industry))).all()
    }
    return [(e, industry_by_entity.get(e.object_id)) for e in edges]


async def _cycle_stats(repo: Repo, at: date | None) -> dict:
    """环路资金统计：复用穿透引擎的环路检测，映射到省份维度。"""
    rows = await repo.flow_rows(at, predicates=_FLOW_PREDICATES)
    region_by_entity: dict[str, str | None] = {
        row[0]: row[1]
        for row in (await repo.session.execute(select(Entity.id, Entity.region_code))).all()
    }
    amount_by_statement: dict[str, int | None] = {r.statement_id: r.amount_scaled for r in rows}
    row_by_pair: dict[frozenset[str], FlowRow] = {}
    graph_edges = [
        GraphEdge(
            statement_id=r.statement_id,
            subject=r.subject_id,
            obj=r.object_id,
            predicate="holds_shares",
            share_scaled=r.share_ratio_scaled,
            voting_scaled=None,
        )
        for r in rows
    ]
    for r in rows:
        row_by_pair[frozenset((r.subject_id, r.object_id))] = r
    cycles = detect_cycles(graph_edges, direction="down", limit=200)
    cross_cycle_edges = 0
    cross_cycle_amount_edges = 0
    seen: set[str] = set()
    for cycle in cycles:
        for i in range(len(cycle) - 1):
            row = row_by_pair.get(frozenset((cycle[i], cycle[i + 1])))
            if row is None or row.statement_id in seen:
                continue
            seen.add(row.statement_id)
            src, dst = region_by_entity.get(row.subject_id), region_by_entity.get(row.object_id)
            if src and dst and src != dst:
                cross_cycle_edges += 1
                if amount_by_statement.get(row.statement_id) is not None:
                    cross_cycle_amount_edges += 1
    return {
        "cycle_count": len(cycles),
        "cross_region_cycle_edges": cross_cycle_edges,
        "cross_region_cycle_amount_edges": cross_cycle_amount_edges,
    }


@router.get("/flows/regions")
async def flows_regions(
    _user: ViewerUser,
    repo: Repo,
    at: date | None = None,
    min_amount_wan: float | None = Query(default=None, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
):
    cross, _ = await _load_flow_edges(repo, at)
    total = len(aggregate_flows(cross, min_amount_wan=min_amount_wan))
    flows = aggregate_flows(cross, min_amount_wan=min_amount_wan, limit=limit)
    return {
        "at": at.isoformat() if at else None,
        "count": total,  # 满足条件的流向总数；returned 为本次实际返回（受 limit 截断）
        "returned": len(flows),
        "flows": [
            {
                "from_region": f.from_region,
                "to_region": f.to_region,
                "edge_count": f.edge_count,
                "amount_edges": f.amount_edges,
                "amount_wan": f.amount_wan,
                "total_share_percent": f.total_share_percent,
                "ratio_missing_edges": f.ratio_missing_edges,
            }
            for f in flows
        ],
    }


@router.get("/flows/summary")
async def flows_summary(_user: ViewerUser, repo: Repo, at: date | None = None):
    _, all_edges = await _load_flow_edges(repo, at)
    summary = region_summary(all_edges)
    summary["cycles"] = await _cycle_stats(repo, at)
    summary["at"] = at.isoformat() if at else None
    return summary


@router.get("/flows/industries")
async def flows_industries(_user: ViewerUser, repo: Repo, at: date | None = None):
    cross, _ = await _load_flow_edges(repo, at)
    result = industry_flows(await _industry_pairs(repo, cross))
    return {"at": at.isoformat() if at else None, **result}


@router.get("/flows/timeline")
async def flows_timeline(_user: ViewerUser, repo: Repo, at: date | None = None):
    cross, _ = await _load_flow_edges(repo, at)
    return {"at": at.isoformat() if at else None, "timeline": flow_timeline(cross)}


@router.get("/flows/compare")
async def flows_compare(
    _user: ViewerUser,
    repo: Repo,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
):
    """区域流动格局对比（切片 B，viewer 可读）：跨省金额/HHI/流向条数差值与流向对增减。"""
    from cg_api.routers.events import resolve_window

    from_date, to_date = resolve_window(from_, to)
    before_cross, before_all = await _load_flow_edges(repo, from_date)
    after_cross, after_all = await _load_flow_edges(repo, to_date)
    result = compare_flows(before_cross, after_cross)
    return {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "algorithm_version": result["algorithm_version"],
        "totals": result["totals"],
        "flows_added": result["flows_added"],
        "flows_removed": result["flows_removed"],
        "flows_changed": result["flows_changed"],
        "flow_pair_delta_check": result["flow_pair_delta_check"],
        "assumptions": list(result["assumptions"]),
        # 单时点摘要（双列视图直接复用）
        "before_summary": region_summary(before_all),
        "after_summary": region_summary(after_all),
    }
