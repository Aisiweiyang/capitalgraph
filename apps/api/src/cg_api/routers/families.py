"""系族路由：系族列表、族详情、族间资本流向（只读聚合，viewer 可读）。

口径沿 ADR-016：控制类边 = controls + 比例 ≥ 阈值的 holds_shares（时点有效），
算法与配置哈希随响应返回，保证结果可追溯、可复现。
"""

from __future__ import annotations

from datetime import date

from cg_capital_graph import (
    FAMILIES_ALGORITHM_VERSION,
    FamiliesConfig,
    FamiliesResult,
    FlowEdge,
    GraphEdge,
    detect_cycles,
    family_flows,
    identify_families,
)
from cg_domain.orm import Entity
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from cg_api.auth import ViewerUser
from cg_api.deps import Repo

router = APIRouter(prefix="/families", tags=["资本系谱"])


async def _load_families(
    repo: Repo, at: date | None, min_control_ratio_percent: float
) -> tuple[FamiliesResult, dict[str, str], dict[str, str], dict[str, str | None], list[GraphEdge]]:
    """加载时点有效边与实体维度，执行系族识别。

    返回 (结果, names, kinds, regions, 原始边)。原始边供详情页重算族内环路。
    """
    rows = await repo.effective_edges(at, predicates=("holds_shares", "controls"))
    edges = [
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
    dim = (
        await repo.session.execute(
            select(Entity.id, Entity.primary_name, Entity.kind, Entity.region_code)
        )
    ).all()
    names: dict[str, str] = {}
    kinds: dict[str, str] = {}
    regions: dict[str, str | None] = {}
    for eid, name, kind, region in dim:
        names[eid] = name
        kinds[eid] = kind
        regions[eid] = region
    config = FamiliesConfig(min_control_ratio_percent=min_control_ratio_percent)
    result = identify_families(edges, kinds, config, region_by_entity=regions)
    return result, names, kinds, regions, edges


def _family_by_entity(result: FamiliesResult) -> dict[str, str]:
    return {m.entity_id: f.family_id for f in result.families for m in f.members}


def _family_summary(fam, names: dict[str, str]) -> dict:
    return {
        "family_id": fam.family_id,
        "controllers": list(fam.controllers),
        "controller_names": [names.get(c, c) for c in fam.controllers],
        "member_count": fam.member_count,
        "region_coverage": fam.region_coverage,
        "regions": [list(r) for r in fam.region_distribution],
        "region_unknown": fam.region_unknown,
        "cycle_count": fam.cycle_count,
        "internal_edge_count": fam.internal_edge_count,
        "density": fam.density,
        "truncated": fam.truncated,
    }


@router.get("")
async def families_list(
    _user: ViewerUser,
    repo: Repo,
    at: date | None = None,
    min_control_ratio_percent: float = Query(default=50.0, ge=0.0, le=100.0),
    sort_by: str = Query(default="size", pattern="^(size|regions|cycles)$"),
    limit: int = Query(default=200, ge=1, le=1000),
):
    result, names, _, _, _ = await _load_families(repo, at, min_control_ratio_percent)
    fams = list(result.families)
    sort_keys = {
        "size": lambda f: (-f.member_count, f.family_id),
        "regions": lambda f: (-f.region_coverage, -f.member_count, f.family_id),
        "cycles": lambda f: (-f.cycle_count, -f.member_count, f.family_id),
    }
    fams.sort(key=sort_keys[sort_by])
    return {
        "at": at.isoformat() if at else None,
        "algorithm_version": FAMILIES_ALGORITHM_VERSION,
        "config_hash": result.config_hash,
        "min_control_ratio_percent": min_control_ratio_percent,
        "count": len(fams),
        "returned": min(len(fams), limit),
        "unassigned_entity_count": result.unassigned_entity_count,
        "missing_ratio_holding_edges": result.missing_ratio_holding_edges,
        "assumptions": list(result.assumptions),
        "families": [_family_summary(f, names) for f in fams[:limit]],
    }


@router.get("/flows")
async def families_flows(
    _user: ViewerUser,
    repo: Repo,
    at: date | None = None,
    min_control_ratio_percent: float = Query(default=50.0, ge=0.0, le=100.0),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """族间资本流向：流动边按（族，族）分组聚合；同族/无族边显式计数。"""
    result, names, _, regions, _ = await _load_families(repo, at, min_control_ratio_percent)
    flow = await repo.flow_rows(at, predicates=("holds_shares", "invests_in"))
    edges = [
        FlowEdge(
            statement_id=r.statement_id,
            from_region=regions.get(r.subject_id) or "",
            to_region=regions.get(r.object_id) or "",
            object_id=r.object_id,
            subject_id=r.subject_id,
            ratio_scaled=r.share_ratio_scaled,
            amount_scaled=r.amount_scaled,
            year=r.valid_from.year,
        )
        for r in flow
    ]
    agg = family_flows(edges, _family_by_entity(result))
    agg["family_names"] = {
        f.family_id: names.get(f.family_id, f.family_id) for f in result.families
    }
    agg["at"] = at.isoformat() if at else None
    agg["count"] = len(agg["rows"])
    agg["rows"] = agg["rows"][:limit]
    return agg


@router.get("/{root}")
async def family_detail(
    root: str,
    _user: ViewerUser,
    repo: Repo,
    at: date | None = None,
    min_control_ratio_percent: float = Query(default=50.0, ge=0.0, le=100.0),
):
    result, names, kinds, regions, edges = await _load_families(repo, at, min_control_ratio_percent)
    fam = next((f for f in result.families if f.family_id == root), None)
    if fam is None:
        raise HTTPException(404, "系族不存在（该实体不是识别到的控制人）")

    fam_ids = {m.entity_id for m in fam.members}
    graph_edges = [
        e
        for e in edges
        if e.subject in fam_ids and e.obj in fam_ids and e.predicate in ("holds_shares", "controls")
    ]
    cycles = detect_cycles(graph_edges, direction="down", limit=100)

    return {
        "at": at.isoformat() if at else None,
        "algorithm_version": FAMILIES_ALGORITHM_VERSION,
        "config_hash": result.config_hash,
        "min_control_ratio_percent": min_control_ratio_percent,
        **_family_summary(fam, names),
        "members": [
            {
                "entity_id": m.entity_id,
                "name": names.get(m.entity_id, m.entity_id),
                "kind": kinds.get(m.entity_id),
                "region_code": regions.get(m.entity_id),
                "controller": m.controller,
                "path": list(m.path),
                "path_names": [names.get(n, n) for n in m.path],
                "depth": m.depth,
                "statement_ids": list(m.statement_ids),
            }
            for m in fam.members
        ],
        "cycles": [[names.get(n, n) for n in cycle] for cycle in cycles],
        "unassigned_entity_count": result.unassigned_entity_count,
        "assumptions": list(result.assumptions),
    }
