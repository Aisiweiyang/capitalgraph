"""实体相关路由：检索、详情、一跳关系、历史、证据。"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from cg_domain.enums import EntityKind
from cg_domain.models import scaled_to_percent
from cg_domain.orm import Entity, Statement
from cg_domain.search_rank import score_name_match
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from cg_api.auth import ViewerUser
from cg_api.deps import Repo
from cg_api.schemas import (
    AliasOut,
    EntityDetailOut,
    EntityHit,
    EvidenceOut,
    HistoryOut,
    IdentifierOut,
    SearchOut,
    SecurityOut,
    StatementOut,
)

router = APIRouter(prefix="/entities", tags=["实体"])


def _redirect_target(entity: Entity) -> str | None:
    return entity.merged_into_id


def statement_out(stmt: Statement) -> StatementOut:
    return StatementOut(
        id=stmt.id,
        subject_id=stmt.subject_id,
        predicate=stmt.predicate,
        object_id=stmt.object_id,
        share_ratio_percent=scaled_to_percent(stmt.share_ratio_scaled),
        voting_ratio_percent=scaled_to_percent(stmt.voting_ratio_scaled),
        control_type=stmt.control_type,
        valid_from=str(stmt.valid_from),
        valid_to=str(stmt.valid_to) if stmt.valid_to else None,
        status=stmt.status,
        claim_basis=stmt.claim_basis,
        confidence=stmt.confidence,
        source_url=stmt.source_url,
        note=stmt.note,
        superseded_by_id=stmt.superseded_by_id,
    )


@router.get("/search", response_model=SearchOut)
async def search_entities(
    repo: Repo,
    _user: ViewerUser,
    q: str = Query(min_length=1, max_length=128),
    kind: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    kinds = [EntityKind(kind)] if kind else None
    # 相关度排序（ADR-003 补记）：取全部命中评分排序后内存分页；
    # 候选上限 1000 与 lookup 分批上限同为文档化规模边界
    all_hits, total = await repo.search(q, kinds=kinds, limit=1000)
    scored = sorted(
        ((score_name_match(q, h.primary_name), h) for h in all_hits),
        key=lambda t: (-t[0], t[1].primary_norm_name),
    )
    page = [h for _, h in scored[offset : offset + limit]]
    relevance_by_id = {h.id: score for score, h in scored}
    if total == 0:
        id_hits = await repo.search_by_identifier(q, limit=limit)
        page = id_hits
        total = len(id_hits)
    return SearchOut(
        total=total,
        hits=[
            EntityHit(
                id=h.id,
                kind=h.kind,
                primary_name=h.primary_name,
                score=relevance_by_id.get(h.id),
            )
            for h in page
        ],
    )


@router.get("/by-region/{code}")
async def entities_by_region(
    repo: Repo,
    _user: ViewerUser,
    code: str,
    limit: int = Query(default=50, ge=1, le=200),
):
    """某省级行政区划下的主体（地图下钻）。仅返回活跃（未合并）主体。"""
    rows = (
        (
            await repo.session.execute(
                select(Entity)
                .where(
                    Entity.region_code == code,
                    Entity.merged_into_id.is_(None),
                )
                .order_by(Entity.primary_name)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "region_code": code,
        "count": len(rows),
        "entities": [
            {
                "id": e.id,
                "kind": e.kind,
                "primary_name": e.primary_name,
                "industry": e.industry,
            }
            for e in rows
        ],
    }


async def _load_entity(repo, entity_id: str) -> Entity:
    entity = await repo.get(entity_id)
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "实体不存在")
    return entity


@router.get("/{entity_id}", response_model=EntityDetailOut)
async def entity_detail(repo: Repo, _user: ViewerUser, entity_id: str):
    entity = await _load_entity(repo, entity_id)
    neighbours = await repo.neighbours(entity_id)
    return EntityDetailOut(
        id=entity.id,
        kind=entity.kind,
        primary_name=entity.primary_name,
        merged_into_id=entity.merged_into_id,
        aliases=[
            AliasOut(name=a.name, alias_type=a.alias_type, lang=a.lang)
            for a in await repo.aliases(entity_id)
        ],
        identifiers=[
            IdentifierOut(namespace=i.namespace, value=i.value)
            for i in await repo.identifiers(entity_id)
        ],
        securities=[
            SecurityOut(code=s.code, exchange=s.exchange, security_type=s.security_type)
            for s in await repo.securities(entity_id)
        ],
        incoming=[statement_out(s) for s in neighbours["incoming"]],
        outgoing=[statement_out(s) for s in neighbours["outgoing"]],
    )


@router.get("/{entity_id}/history", response_model=HistoryOut)
async def entity_history(repo: Repo, _user: ViewerUser, entity_id: str):
    """与该实体相关的全部声明（含 superseded/retracted），按时间排序。"""
    await _load_entity(repo, entity_id)
    from cg_domain.orm import Statement
    from sqlalchemy import select

    rows = (
        (
            await repo.session.execute(
                select(Statement)
                .where((Statement.subject_id == entity_id) | (Statement.object_id == entity_id))
                .order_by(Statement.valid_from, Statement.recorded_at)
            )
        )
        .scalars()
        .all()
    )
    return HistoryOut(statements=[statement_out(s) for s in rows])


@router.get("/{entity_id}/evidence", response_model=EvidenceOut)
async def statement_evidence(repo: Repo, _user: ViewerUser, entity_id: str, statement_id: str):
    """指定声明的证据片段（快照哈希、来源 URL、原始值）。"""
    evidence = await repo.evidence_for_statements([statement_id])
    fragments = evidence.get(statement_id, [])
    return EvidenceOut(statement_id=statement_id, fragments=fragments)


@router.get("/{entity_id}/events")
async def entity_events(
    repo: Repo,
    _user: ViewerUser,
    entity_id: str,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
):
    """单实体变更轨迹（切片 A）：该实体在 from/to 两时点间的声明层面变化摘要。"""
    from cg_capital_graph import events_for_entity

    from cg_api.routers.events import entity_names, event_out, load_events

    await _load_entity(repo, entity_id)
    result, from_date, to_date = await load_events(repo, from_, to)
    events = events_for_entity(result.events, entity_id)
    names = await entity_names(repo, {e.subject_id for e in events} | {e.object_id for e in events})
    counts: dict[str, int] = {}
    for e in events:
        counts[e.event_type] = counts.get(e.event_type, 0) + 1
    return {
        "entity_id": entity_id,
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "algorithm_version": result.algorithm_version,
        "total": len(events),
        "counts_by_type": [{"event_type": t, "count": n} for t, n in sorted(counts.items())],
        "assumptions": list(result.assumptions),
        "events": [event_out(e, names) for e in events],
    }


@router.get("/{entity_id}/shareholders")
async def shareholders(
    repo: Repo,
    _user: ViewerUser,
    entity_id: str,
    at: date | None = None,
):
    """直接股东（时点）。持股与控制分开返回。"""
    await _load_entity(repo, entity_id)
    edges = await repo.effective_edges(at)
    holders = {}
    controls = []
    for edge in edges:
        if edge.object_id != entity_id:
            continue
        if edge.predicate == "holds_shares":
            holders[edge.subject_id] = {
                "shareholder_id": edge.subject_id,
                "share_ratio_percent": scaled_to_percent(edge.share_ratio_scaled),
                "voting_ratio_percent": scaled_to_percent(edge.voting_ratio_scaled),
                "statement_id": edge.statement_id,
                "ratio_unknown": edge.share_ratio_scaled is None,
            }
        elif edge.predicate == "controls":
            controls.append({"shareholder_id": edge.subject_id, "statement_id": edge.statement_id})
    names = await _names(repo, list(holders))
    result = list(holders.values())
    for item in result:
        item["name"] = names.get(str(item["shareholder_id"]), "")
    return {
        "entity_id": entity_id,
        "at": str(at) if at else None,
        "shareholders": result,
        "controls": controls,
    }


@router.get("/{entity_id}/investments")
async def investments(
    repo: Repo,
    _user: ViewerUser,
    entity_id: str,
    at: date | None = None,
):
    await _load_entity(repo, entity_id)
    edges = await repo.effective_edges(at)
    rows = {}
    for edge in edges:
        if edge.subject_id != entity_id or edge.predicate != "holds_shares":
            continue
        rows[edge.object_id] = {
            "target_id": edge.object_id,
            "share_ratio_percent": scaled_to_percent(edge.share_ratio_scaled),
            "statement_id": edge.statement_id,
            "ratio_unknown": edge.share_ratio_scaled is None,
        }
    names = await _names(repo, list(rows))
    result = list(rows.values())
    for item in result:
        item["name"] = names.get(str(item["target_id"]), "")
    return {"entity_id": entity_id, "at": str(at) if at else None, "investments": result}


async def _names(repo, entity_ids: list[str]) -> dict[str, str]:
    from cg_domain.orm import Entity
    from sqlalchemy import select

    if not entity_ids:
        return {}
    rows = await repo.session.execute(
        select(Entity.id, Entity.primary_name).where(Entity.id.in_(entity_ids))
    )
    return dict(rows.all())
