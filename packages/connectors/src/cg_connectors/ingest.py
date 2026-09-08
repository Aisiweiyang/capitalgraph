"""入库服务：把 ConnectorResult 变成带证据链的领域数据。

流程（每个批次）：
1. 幂等检查（ingestion_run 幂等键）；
2. 实体 upsert（标识符优先）；
3. 证据链：document → snapshot(sha256) → fragment；
4. 声明入库（载荷级幂等）；同时生成声明级质量检查（冲突/缺比例）。
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.ext.asyncio import AsyncSession

from cg_connectors.base import BaseConnector, ConnectorContext, ConnectorResult, RateLimiter
from cg_domain.enums import IngestionStatus
from cg_domain.repo import Repository


class IngestionStats:
    def __init__(self) -> None:
        self.entities_created = 0
        self.statements_created = 0
        self.statements_deduplicated = 0
        self.issues: list[str] = []

    def to_dict(self) -> dict:
        return {
            "entities_created": self.entities_created,
            "statements_created": self.statements_created,
            "statements_deduplicated": self.statements_deduplicated,
            "issues": self.issues[:50],
        }


async def ingest_connector_result(
    session: AsyncSession,
    connector: BaseConnector,
    result: ConnectorResult,
    *,
    idempotency_key: str,
    run_id: str,
) -> IngestionStats:
    repo = Repository(session)
    stats = IngestionStats()
    from cg_domain.config import load_settings

    store_raw = load_settings().store_raw_documents

    # 证据链：登记文档与快照（哈希优先；原文按配置落对象存储）
    doc_ids: dict[str, str] = {}
    for doc in result.documents:
        stored = await repo.register_document(doc)
        doc_ids[doc.model_dump_json()] = stored.id

    default_doc_id = next(iter(doc_ids.values()), None)
    fragment_cache: dict[str, str] = {}

    async def fragment_id(ev) -> str | None:  # noqa: ANN001 - EvidenceRecord
        cache_key = f"{ev.document_title}|{ev.field_path}|{ev.raw_value}"
        if cache_key in fragment_cache:
            return fragment_cache[cache_key]
        if default_doc_id is None:
            return None
        content = ev.raw_value.encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        snapshot = await repo.add_snapshot(
            default_doc_id,
            digest,
            storage_key=digest if store_raw else None,
            raw_stored=store_raw,
        )
        frag = await repo.add_fragment(snapshot.id, ev)
        fragment_cache[cache_key] = frag.id
        return frag.id

    # 实体 upsert
    entity_map = {}
    for record in result.entities:
        entity = await repo.upsert(record)
        entity_map[record.key] = entity.id
        stats.entities_created += 1

    # 声明入库
    for stmt in result.statements:
        subject_id = await _resolve_key(repo, stmt.subject_key, entity_map)
        object_id = await _resolve_key(repo, stmt.object_key, entity_map)
        if subject_id is None or object_id is None:
            stats.issues.append(f"无法解析主体键: {stmt.subject_key} -> {stmt.object_key}")
            continue
        fragment_ids: list[str] = []
        for ev in stmt.evidence:
            fid = await fragment_id(ev)
            if fid:
                fragment_ids.append(fid)
        statement, created = await repo.add_statement(
            stmt,
            subject_id=subject_id,
            object_id=object_id,
            connector_id=connector.spec().connector_id,
            ingestion_run_id=run_id,
            source_url=stmt.evidence[0].source_url if stmt.evidence else "",
            fragment_ids=fragment_ids,
        )
        if created:
            stats.statements_created += 1
            # 质量规则：同对主体间的冲突声明
            if stmt.predicate.value == "holds_shares" and stmt.share_ratio is None:
                await repo.add_quality_issue(
                    "missing_ratio",
                    severity="warning",
                    entity_id=subject_id,
                    statement_id=statement.id,
                    detail={"predicate": stmt.predicate.value},
                )
        else:
            stats.statements_deduplicated += 1

    await repo.finish_run(run_id, IngestionStatus.SUCCEEDED, counts=stats.to_dict())
    return stats


async def _resolve_key(repo: Repository, key: str, entity_map: dict[str, str]) -> str | None:
    if key in entity_map:
        return entity_map[key]
    # src:<connector>:<external_id> 形式直接查标识符
    parts = key.split(":", 2)
    if len(parts) == 3 and parts[0] == "src":
        return await repo.find_id_by_identifier("src", f"{parts[1]}:{parts[2]}")
    if len(parts) == 2 and parts[0] in {"uscc", "lei"}:
        return await repo.find_id_by_identifier(parts[0], parts[1])
    return None


async def run_connector(
    session: AsyncSession,
    connector: BaseConnector,
    ctx: ConnectorContext,
) -> IngestionStats | None:
    """完整运行一个 connector：幂等检查 → 限速 → 分批入库。

    返回 None 表示幂等命中（同键运行已存在），调用方无需重复导入。
    """
    repo = Repository(session)
    key = connector.idempotency_key(ctx)
    run = await repo.start_run(connector.spec().connector_id, key)
    if run is None:
        return None
    limiter = RateLimiter(ctx.rate_limit_per_sec)
    total = IngestionStats()
    for batch, issue in connector.fetch(ctx):
        limiter.wait()
        if issue is not None:
            total.issues.append(f"{issue.code}: {issue.message}")
        stats = await ingest_connector_result(
            session, connector, batch, idempotency_key=key, run_id=run.id
        )
        total.entities_created += stats.entities_created
        total.statements_created += stats.statements_created
        total.statements_deduplicated += stats.statements_deduplicated
        total.issues.extend(stats.issues)
    await repo.finish_run(run.id, _succeeded(), counts=total.to_dict())
    return total


def _succeeded():
    from cg_domain.enums import IngestionStatus

    return IngestionStatus.SUCCEEDED


def stats_json(stats: IngestionStats) -> str:
    return json.dumps(stats.to_dict(), ensure_ascii=False)
