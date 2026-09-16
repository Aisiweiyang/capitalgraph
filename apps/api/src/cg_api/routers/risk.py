"""风险传导路由：担保链/互保圈查询、传导模拟、RiskFlag 计算与列表。

口径（ADR-016）：
- 担保边 = 时点有效的 provides_guarantee 声明（subject=担保人，object=被担保人），
  金额用结构化 amount_scaled，缺失金额显式计数；
- "出险"定义 = 被标 open 状态 RiskFlag 的实体（可用 distressed 参数显式指定做模拟）；
- compute 仅登记算法候选标记（guarantee_cycle / guarantee_chain_exposure），
  payload 记录输入摘要/算法版本/配置哈希，幂等去重：同 (类型, 主体, 输入摘要) 的
  open 标记不重复创建；
- 所有结果均为算法候选，仅供研究参考，不构成信用、法律或投资结论。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from cg_capital_graph import (
    RISK_CHAINS_ALGORITHM_VERSION,
    GuaranteeEdge,
    RiskChainsConfig,
    guarantee_chains,
    guarantee_cycles,
    input_digest,
    propagate_risk,
)
from cg_domain.config import load_settings
from cg_domain.enums import FlagType
from cg_domain.orm import Entity
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from cg_api.auth import AnalystUser, ViewerUser
from cg_api.deps import Repo

router = APIRouter(prefix="/risk", tags=["风险传导"])

_AMOUNT_WAN_PER_SCALED = 0.01

RISK_ASSUMPTIONS = (
    "担保边 = 时点有效的 provides_guarantee 声明；名义金额取结构化金额，缺失不补值；",
    "传导方向 = 义务方向（被担保方出险 → 担保方受累）；",
    '"出险"定义 = 被标 open 状态 RiskFlag 的实体（或调用方显式指定做模拟）；',
    "结果为算法候选，仅供研究参考，不构成信用、法律或投资结论。",
)


def _wan(scaled: int | None) -> float | None:
    return None if scaled is None else round(scaled * _AMOUNT_WAN_PER_SCALED, 2)


async def _guarantee_edges(repo: Repo, at: date | None) -> list[GuaranteeEdge]:
    rows = await repo.flow_rows(at, predicates=("provides_guarantee",))
    return [
        GuaranteeEdge(
            statement_id=r.statement_id,
            guarantor=r.subject_id,
            beneficiary=r.object_id,
            amount_scaled=r.amount_scaled,
        )
        for r in rows
    ]


async def _names(repo: Repo, entity_ids: set[str]) -> dict[str, str]:
    if not entity_ids:
        return {}
    rows = await repo.session.execute(
        select(Entity.id, Entity.primary_name).where(Entity.id.in_(entity_ids))
    )
    return dict((row[0], row[1]) for row in rows.all())


def _config() -> RiskChainsConfig:
    defaults = load_settings().penetration
    # 与穿透共用护栏心智：深度走独立默认，上限沿用穿透护栏的保守界
    return RiskChainsConfig(max_depth=min(6, max(1, int(defaults.max_depth))))


@router.get("/chains/{entity_id}")
async def risk_chains(
    entity_id: str,
    _user: ViewerUser,
    repo: Repo,
    at: date | None = None,
):
    """某主体的担保链条、涉及互保圈、传导模拟与质押敞口（viewer 可读）。"""
    entity = await repo.get(entity_id)
    if entity is None:
        raise HTTPException(404, "实体不存在")
    edges = await _guarantee_edges(repo, at)
    cfg = _config()
    digest = input_digest(edges)

    involved = {e.guarantor for e in edges} | {e.beneficiary for e in edges}
    names = await _names(repo, involved | {entity_id})

    chains = guarantee_chains(edges, entity_id, cfg)
    all_cycles = guarantee_cycles(edges, cfg)
    name_of = lambda eid: names.get(eid, eid)  # noqa: E731
    cycles_of_entity = [c for c in all_cycles if entity_id in c]
    propagation = propagate_risk(edges, {entity_id}, cfg)
    pledge_rows = await repo.flow_rows(at, predicates=("pledges_shares",))
    pledges = [r for r in pledge_rows if entity_id in (r.subject_id, r.object_id)]
    pledge_names = await _names(
        repo, {r.subject_id for r in pledges} | {r.object_id for r in pledges}
    )

    return {
        "entity_id": entity_id,
        "entity_name": names.get(entity_id, entity.primary_name),
        "at": at.isoformat() if at else None,
        "algorithm_version": RISK_CHAINS_ALGORITHM_VERSION,
        "config_hash": cfg.canonical_hash(),
        "input_digest": digest,
        "guarantee_edge_count": len(edges),
        "chains": [
            {
                "path": [name_of(n) for n in c.path],
                "path_ids": list(c.path),
                "statement_ids": list(c.statement_ids),
                "nominal_amount_wan": _wan(c.nominal_amount_scaled),
                "amount_missing_edges": c.amount_missing_edges,
            }
            for c in chains
        ],
        "cycles": [[name_of(n) for n in c] for c in cycles_of_entity],
        "propagation": {
            "origin": [name_of(n) for n in propagation.origin],
            "levels": [
                {
                    "depth": lv.depth,
                    "newly_affected": [name_of(n) for n in lv.newly_affected],
                    "newly_affected_ids": list(lv.newly_affected),
                    "nominal_amount_wan": _wan(lv.nominal_amount_scaled),
                    "amount_missing_edges": lv.amount_missing_edges,
                }
                for lv in propagation.levels
            ],
            "affected_entities": [name_of(n) for n in propagation.affected_entities],
            "affected_entity_ids": list(propagation.affected_entities),
            "total_nominal_wan": _wan(propagation.total_nominal_scaled),
            "total_amount_missing_edges": propagation.total_amount_missing_edges,
        },
        "pledges": [
            {
                "statement_id": r.statement_id,
                "pledgor_id": r.subject_id,
                "target_id": r.object_id,
                "pledgor": pledge_names.get(r.subject_id, r.subject_id),
                "target": pledge_names.get(r.object_id, r.object_id),
                "share_percent": (
                    round(r.share_ratio_scaled * 100.0 / 10**8, 6)
                    if r.share_ratio_scaled is not None
                    else None
                ),
                "amount_wan": _wan(r.amount_scaled),
            }
            for r in pledges
        ],
        "assumptions": list(RISK_ASSUMPTIONS),
    }


@router.get("/flags")
async def risk_flags(
    _user: ViewerUser,
    repo: Repo,
    limit: int = Query(default=100, ge=1, le=500),
):
    """风险标记列表（算法候选；复核队列页面消费）。"""
    flags = await repo.list_risk_flags(limit=limit)
    ids = {f.subject_entity_id for f in flags if f.subject_entity_id}
    names = await _names(repo, ids)
    return [
        {
            "id": f.id,
            "flag_type": f.flag_type,
            "subject_entity_id": f.subject_entity_id,
            "subject_name": names.get(f.subject_entity_id or "", ""),
            "payload": json.loads(f.payload_json or "{}"),
            "status": f.status,
            "created_at": str(f.created_at),
        }
        for f in flags
    ]


@router.post("/compute")
async def risk_compute(
    _user: AnalystUser,
    repo: Repo,
    at: date | None = None,
    distressed: str | None = Query(default=None, description="逗号分隔实体ID，显式出险集合"),
):
    """全图担保风险计算并登记 RiskFlag（analyst+，幂等去重）。"""
    edges = await _guarantee_edges(repo, at)
    cfg = _config()
    digest = input_digest(edges)
    involved = {e.guarantor for e in edges} | {e.beneficiary for e in edges}
    names = await _names(repo, involved)

    # 已有 open 标记去重键：(类型, 主体, 输入摘要)
    existing = await repo.list_risk_flags(
        flag_types=(FlagType.GUARANTEE_CYCLE, FlagType.GUARANTEE_CHAIN_EXPOSURE), limit=1000
    )
    existing_keys = {
        (f.flag_type, f.subject_entity_id, json.loads(f.payload_json or "{}").get("input_digest"))
        for f in existing
    }

    async def _flag_once(flag_type: str, subject: str, payload: dict) -> int:
        key = (flag_type, subject, payload.get("input_digest"))
        if key in existing_keys:
            return 0
        await repo.add_risk_flag(flag_type, subject_entity_id=subject, payload=payload)
        existing_keys.add(key)  # type: ignore[arg-type]
        return 1

    cycles = guarantee_cycles(edges, cfg)
    cycle_created = 0
    cycle_subjects: set[str] = set()
    payload: dict[str, Any]
    for cycle in cycles:
        payload = {
            "cycle": list(cycle),
            "cycle_names": [names.get(n, n) for n in cycle],
            "input_digest": digest,
            "algorithm_version": RISK_CHAINS_ALGORITHM_VERSION,
            "config_hash": cfg.canonical_hash(),
            "note": "互保圈（算法候选）",
        }
        subject = min(cycle)
        cycle_subjects.add(subject)
        cycle_created += await _flag_once(FlagType.GUARANTEE_CYCLE.value, subject, payload)

    # 出险集合：显式参数优先，否则取 open 标记涉及主体（含刚登记的互保圈）
    if distressed:
        wanted = [x.strip() for x in distressed.split(",") if x.strip()]
        unknown = [x for x in wanted if x not in involved]
        if unknown:
            raise HTTPException(422, f"出险实体不在担保网络中: {','.join(unknown[:5])}")
        seeds = set(wanted)
    else:
        flagged = await repo.open_risk_flag_subjects()
        seeds = set(flagged) & involved
    seeds |= cycle_subjects

    exposure_created = 0
    propagation_summary: dict[str, int] = {}
    for origin in sorted(seeds):
        prop = propagate_risk(edges, {origin}, cfg)
        if not prop.affected_entities:
            continue
        propagation_summary[origin] = len(prop.affected_entities)
        for level in prop.levels:
            for affected in level.newly_affected:
                payload = {
                    "origin": origin,
                    "origin_name": names.get(origin, origin),
                    "depth": level.depth,
                    "via_statement_ids": [],  # 传导层不绑定单条声明，金额为该层合计
                    "level_nominal_amount_wan": _wan(level.nominal_amount_scaled),
                    "level_amount_missing_edges": level.amount_missing_edges,
                    "affected_count": len(prop.affected_entities),
                    "input_digest": digest,
                    "algorithm_version": RISK_CHAINS_ALGORITHM_VERSION,
                    "config_hash": cfg.canonical_hash(),
                    "note": "担保链传导受累（算法候选）",
                }
                exposure_created += await _flag_once(
                    FlagType.GUARANTEE_CHAIN_EXPOSURE.value, affected, payload
                )

    await repo.audit(
        actor=_user["username"],
        action="risk.compute",
        target=f"guarantee_graph@{at.isoformat() if at else 'current'}",
        result="ok",
        detail={
            "cycles": len(cycles),
            "cycle_flags": cycle_created,
            "exposure_flags": exposure_created,
            "input_digest": digest,
        },
    )
    return {
        "at": at.isoformat() if at else None,
        "algorithm_version": RISK_CHAINS_ALGORITHM_VERSION,
        "config_hash": cfg.canonical_hash(),
        "input_digest": digest,
        "guarantee_edge_count": len(edges),
        "cycles_found": len(cycles),
        "cycle_flags_created": cycle_created,
        "exposure_flags_created": exposure_created,
        "distressed_used": sorted(seeds),
        "propagation_affected": propagation_summary,
    }
