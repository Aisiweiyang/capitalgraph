"""实体相关路由：检索、详情、一跳关系、历史、证据。"""

from __future__ import annotations

from datetime import date

from cg_domain.enums import EntityKind
from cg_domain.models import scaled_to_percent
from cg_domain.orm import Entity, Statement
from fastapi import APIRouter, HTTPException, Query, status

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
    hits, total = await repo.search(q, kinds=kinds, limit=limit, offset=offset)
    if total == 0:
        id_hits = await repo.search_by_identifier(q, limit=limit)
        hits = id_hits
        total = len(id_hits)
    return SearchOut(
        total=total,
        hits=[EntityHit(id=h.id, kind=h.kind, primary_name=h.primary_name) for h in hits],
    )


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
        item["name"] = names.get(item["shareholder_id"], "")
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
        item["name"] = names.get(item["target_id"], "")
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
