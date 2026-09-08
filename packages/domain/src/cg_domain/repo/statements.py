"""声明仓储：证据链落库、幂等入库与时态 supersede、时点快照加载。

supersede 语义：同一 (subject, predicate, object, valid_from) 且载荷变化时，
旧 active 声明转 superseded 并指向新声明；载荷与区间完全一致则幂等跳过。
历史答案由 valid 区间 + recorded_at 共同保证，永不覆盖。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cg_domain.enums import IngestionStatus, StatementStatus
from cg_domain.models import DocumentRef, EvidenceRecord, StatementRecord
from cg_domain.orm import (
    EvidenceFragment,
    IngestionRun,
    SourceDocument,
    SourceSnapshot,
    Statement,
    StatementEvidence,
)


@dataclass(frozen=True)
class EdgeRow:
    """图算法输入边。来自时点过滤后的 active 声明。"""

    statement_id: str
    subject_id: str
    object_id: str
    predicate: str
    share_ratio_scaled: int | None
    voting_ratio_scaled: int | None


class StatementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------- 来源链

    async def register_document(self, ref: DocumentRef) -> SourceDocument:
        doc = SourceDocument(
            connector_id=ref.connector_id,
            title=ref.title,
            source_url=ref.source_url,
            notes=ref.notes,
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def add_snapshot(
        self,
        document_id: str,
        content_sha256: str,
        *,
        storage_key: str | None = None,
        http_status: int | None = None,
        raw_stored: bool = False,
    ) -> SourceSnapshot:
        snap = SourceSnapshot(
            document_id=document_id,
            content_sha256=content_sha256,
            storage_key=storage_key,
            http_status=http_status,
            raw_stored=raw_stored,
        )
        self.session.add(snap)
        await self.session.flush()
        return snap

    async def add_fragment(
        self, snapshot_id: str, ev: EvidenceRecord
    ) -> EvidenceFragment:
        frag = EvidenceFragment(
            snapshot_id=snapshot_id,
            field_path=ev.field_path,
            raw_value=ev.raw_value,
            normalized_value=ev.normalized_value,
            page_ref=ev.page_ref,
        )
        self.session.add(frag)
        await self.session.flush()
        return frag

    async def start_run(
        self, connector_id: str, idempotency_key: str, params_hash: str = ""
    ) -> IngestionRun | None:
        """幂等运行登记：同键运行存在则返回 None（调用方跳过或查询结果）。"""
        existing = await self.session.execute(
            select(IngestionRun).where(IngestionRun.idempotency_key == idempotency_key).limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            return None
        run = IngestionRun(
            connector_id=connector_id,
            idempotency_key=idempotency_key,
            params_hash=params_hash,
            status=IngestionStatus.RUNNING.value,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def finish_run(self, run_id: str, status: IngestionStatus, summary: str = "", counts: dict | None = None) -> None:
        run = await self.session.get(IngestionRun, run_id)
        if run is None:
            return
        run.status = status.value
        run.finished_at = datetime.now().astimezone()
        run.error_summary = summary[:2000]
        run.counts_json = json.dumps(counts or {}, ensure_ascii=False)
        await self.session.flush()

    # ------------------------------------------------------------- 声明入库

    @staticmethod
    def _payload_fingerprint(stmt: StatementRecord, subject_id: str, object_id: str) -> str:
        payload = {
            "s": subject_id,
            "p": stmt.predicate.value,
            "o": object_id,
            "vf": stmt.valid_from.isoformat(),
            "vt": stmt.valid_to.isoformat() if stmt.valid_to else None,
            "share": stmt.share_ratio_scaled,
            "voting": stmt.voting_ratio_scaled,
            "ct": stmt.control_type.value if stmt.control_type else None,
            "amount": stmt.amount,
            "class": stmt.share_class,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    async def add_statement(
        self,
        record: StatementRecord,
        *,
        subject_id: str,
        object_id: str,
        connector_id: str,
        ingestion_run_id: str | None,
        source_url: str = "",
        fragment_ids: list[str] | None = None,
    ) -> tuple[Statement, bool]:
        """返回 (声明, 是否新插入)。幂等：重复载荷不重复入库。"""
        fingerprint = self._payload_fingerprint(record, subject_id, object_id)
        rows = (
            (
                await self.session.execute(
                    select(Statement).where(
                        Statement.subject_id == subject_id,
                        Statement.predicate == record.predicate.value,
                        Statement.object_id == object_id,
                        Statement.valid_from == record.valid_from,
                        Statement.status.in_(
                            [StatementStatus.ACTIVE.value, StatementStatus.PENDING_REVIEW.value]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for existing in rows:
            same_payload = (
                existing.share_ratio_scaled == record.share_ratio_scaled
                and existing.voting_ratio_scaled == record.voting_ratio_scaled
                and existing.control_type == (record.control_type.value if record.control_type else None)
                and existing.valid_to == record.valid_to
            )
            if same_payload:
                return existing, False
        statement = Statement(
            subject_id=subject_id,
            predicate=record.predicate.value,
            object_id=object_id,
            share_ratio_scaled=record.share_ratio_scaled,
            voting_ratio_scaled=record.voting_ratio_scaled,
            ratio_unit_original=record.ratio_unit.value,
            control_type=record.control_type.value if record.control_type else None,
            share_class=record.share_class,
            amount=record.amount,
            currency=record.currency,
            valid_from=record.valid_from,
            valid_to=record.valid_to,
            recorded_at=record.recorded_at or datetime.now().astimezone(),
            status=StatementStatus.ACTIVE.value,
            claim_basis=record.claim_basis.value,
            confidence=record.confidence,
            connector_id=connector_id,
            ingestion_run_id=ingestion_run_id,
            source_url=source_url,
            note=record.note,
        )
        self.session.add(statement)
        await self.session.flush()
        for fid in fragment_ids or []:
            self.session.add(
                StatementEvidence(statement_id=statement.id, evidence_fragment_id=fid)
            )
        await self.session.flush()
        return statement, True

    async def supersede(self, old_id: str, new_id: str) -> None:
        old = await self.session.get(Statement, old_id)
        if old is None:
            return
        old.status = StatementStatus.SUPERSEDED.value
        old.superseded_by_id = new_id
        await self.session.flush()

    async def retracted_statements_for(self, subject_id: str, object_id: str) -> list[Statement]:
        """同主体对间互相冲突的 active 声明（供冲突检测与复核队列）。"""
        rows = (
            (
                await self.session.execute(
                    select(Statement).where(
                        Statement.subject_id == subject_id,
                        Statement.object_id == object_id,
                        Statement.status == StatementStatus.ACTIVE.value,
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    # ------------------------------------------------------------- 时点快照

    async def effective_edges(
        self, at: date | None = None, predicates: tuple[str, ...] = ("holds_shares", "controls")
    ) -> list[EdgeRow]:
        """某时点有效的边（左闭右开）。at=None 表示当前。

        面向中等问题规模的一次性加载；更大规模按连通分量扩展是后续优化项。
        """
        at_date = at or date.today()
        rows = await self.session.execute(
            select(
                Statement.id,
                Statement.subject_id,
                Statement.object_id,
                Statement.predicate,
                Statement.share_ratio_scaled,
                Statement.voting_ratio_scaled,
            ).where(
                Statement.status == StatementStatus.ACTIVE.value,
                Statement.predicate.in_(list(predicates)),
                Statement.valid_from <= at_date,
                or_(Statement.valid_to.is_(None), Statement.valid_to > at_date),
            )
        )
        return [EdgeRow(*row) for row in rows.all()]

    async def statement_history(self, subject_id: str, object_id: str) -> list[Statement]:
        rows = (
            (
                await self.session.execute(
                    select(Statement)
                    .where(
                        Statement.subject_id == subject_id,
                        Statement.object_id == object_id,
                    )
                    .order_by(Statement.valid_from, Statement.recorded_at)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def evidence_for_statements(self, statement_ids: list[str]) -> dict[str, list[dict]]:
        """statement_id → 证据片段列表（含快照哈希与文档 URL）。"""
        if not statement_ids:
            return {}
        rows = await self.session.execute(
            select(StatementEvidence, EvidenceFragment, SourceSnapshot, SourceDocument)
            .join(
                EvidenceFragment,
                EvidenceFragment.id == StatementEvidence.evidence_fragment_id,
            )
            .join(SourceSnapshot, SourceSnapshot.id == EvidenceFragment.snapshot_id)
            .join(SourceDocument, SourceDocument.id == SourceSnapshot.document_id)
            .where(StatementEvidence.statement_id.in_(statement_ids))
        )
        result: dict[str, list[dict]] = {}
        for link, frag, snap, doc in rows.all():
            result.setdefault(link.statement_id, []).append(
                {
                    "fragment_id": frag.id,
                    "field_path": frag.field_path,
                    "raw_value": frag.raw_value,
                    "normalized_value": frag.normalized_value,
                    "page_ref": frag.page_ref,
                    "content_sha256": snap.content_sha256,
                    "raw_stored": snap.raw_stored,
                    "source_url": doc.source_url,
                    "document_title": doc.title,
                }
            )
        return result
