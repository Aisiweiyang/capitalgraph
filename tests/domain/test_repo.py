"""仓储层测试：实体 upsert 幂等、声明幂等、时点快照、审计与任务。"""

from datetime import date

from cg_connectors.base import ConnectorContext
from cg_connectors.ingest import run_connector
from cg_connectors.synthetic import SyntheticConnector
from cg_domain.enums import Predicate, RatioUnit, StatementStatus, TaskStatus
from cg_domain.models import (
    DocumentRef,
    EntityRecord,
    EvidenceRecord,
    StatementRecord,
)
from cg_domain.repo import Repository


async def make_entity(repo: Repository, ext: str, name: str, uscc: str | None = None):
    return await repo.upsert(
        EntityRecord(
            connector_id="synthetic",
            external_id=ext,
            name=name,
            uscc=uscc,
        )
    )


async def test_entity_upsert_idempotent_by_identifier(db_session):
    repo = Repository(db_session)
    first = await make_entity(repo, "C1", "华康科技有限公司", "91110000ABCDEF01X9")
    again = await make_entity(repo, "C1", "华康科技有限公司", "91110000ABCDEF01X9")
    assert first.id == again.id
    # 不同来源键、相同 USCC → 同一实体
    other_record = EntityRecord(
        connector_id="other", external_id="ZZ", name="华康科技有限公司", uscc="91110000ABCDEF01X9"
    )
    merged = await repo.upsert(other_record)
    assert merged.id == first.id


async def test_statement_idempotent_and_history(db_session):
    repo = Repository(db_session)
    a = await make_entity(repo, "P1", "张三")
    b = await make_entity(repo, "C1", "甲公司")

    def stmt(valid_from=date(2020, 1, 1), ratio=60.0):
        return StatementRecord(
            subject_key="src:synthetic:P1",
            predicate=Predicate.HOLDS_SHARES,
            object_key="src:synthetic:C1",
            valid_from=valid_from,
            share_ratio=ratio,
            ratio_unit=RatioUnit.PERCENT,
            evidence=[EvidenceRecord(field_path="x", raw_value="60%")],
        )

    s1, created1 = await repo.add_statement(
        stmt(), subject_id=a.id, object_id=b.id, connector_id="t", ingestion_run_id=None
    )
    s2, created2 = await repo.add_statement(
        stmt(), subject_id=a.id, object_id=b.id, connector_id="t", ingestion_run_id=None
    )
    assert created1 and not created2
    assert s1.id == s2.id
    # 同期不同比例 → 新声明 + 旧声明 superseded
    s3, created3 = await repo.add_statement(
        stmt(ratio=55.0), subject_id=a.id, object_id=b.id, connector_id="t", ingestion_run_id=None
    )
    assert created3
    await repo.supersede(s1.id, s3.id)
    history = await repo.statement_history(a.id, b.id)
    assert len(history) == 2
    statuses = {s.id: s.status for s in history}
    assert statuses[s1.id] == StatementStatus.SUPERSEDED.value
    assert statuses[s3.id] == StatementStatus.ACTIVE.value


async def test_effective_edges_respect_time_point(db_session):
    repo = Repository(db_session)
    person = await make_entity(repo, "P1", "张三")
    company = await make_entity(repo, "C1", "甲公司")
    old = StatementRecord(
        subject_key="src:synthetic:P1",
        predicate=Predicate.HOLDS_SHARES,
        object_key="src:synthetic:C1",
        valid_from=date(2018, 1, 1),
        valid_to=date(2022, 5, 31),
        share_ratio=60.0,
        ratio_unit=RatioUnit.PERCENT,
    )
    new = StatementRecord(
        subject_key="src:synthetic:P1",
        predicate=Predicate.HOLDS_SHARES,
        object_key="src:synthetic:C1",
        valid_from=date(2022, 6, 1),
        share_ratio=10.0,
        ratio_unit=RatioUnit.PERCENT,
    )
    # 不同 valid_from → 两条并存（历史期间各自成立）
    await repo.add_statement(
        old, subject_id=person.id, object_id=company.id, connector_id="t", ingestion_run_id=None
    )
    await repo.add_statement(
        new, subject_id=person.id, object_id=company.id, connector_id="t", ingestion_run_id=None
    )

    at_2020 = await repo.effective_edges(date(2020, 6, 30))
    at_2023 = await repo.effective_edges(date(2023, 1, 1))
    at_2022_6_1 = await repo.effective_edges(date(2022, 6, 1))
    assert len(at_2020) == 1 and at_2020[0].share_ratio_scaled == round(0.6 * 10**8)
    assert len(at_2023) == 1 and at_2023[0].share_ratio_scaled == round(0.1 * 10**8)
    # 左闭右开：旧声明 valid_to=2022-05-31 为开区间上界，5-31 当天已失效、5-30 仍有效
    assert await repo.effective_edges(date(2022, 5, 31)) == []
    at_5_30 = await repo.effective_edges(date(2022, 5, 30))
    assert at_5_30[0].share_ratio_scaled == round(0.6 * 10**8)
    assert at_2022_6_1[0].share_ratio_scaled == round(0.1 * 10**8)


async def test_audit_append_and_review_flow(db_session):
    repo = Repository(db_session)
    await repo.audit(actor="tester", action="ingest", target="synthetic", result="ok")
    await repo.audit(actor="tester", action="search", result="ok")
    tail = await repo.audit_tail()
    assert len(tail) == 2

    item = await repo.add_review_item("conflict", {"statement": "s1"})
    resolved = await repo.resolve_review_item(item.id, "确认无误", "admin")
    assert resolved.status == "resolved"
    assert resolved.assignee == "admin"


async def test_task_idempotent_enqueue_and_backoff(db_session):
    repo = Repository(db_session)
    t1 = await repo.enqueue_task("ingest", "key-1", {"connector": "synthetic"})
    t2 = await repo.enqueue_task("ingest", "key-1", {"connector": "synthetic"})
    assert t1 is not None and t2 is None

    claimed = await repo.claim_next_task()
    assert claimed is not None and claimed.status == TaskStatus.RUNNING.value
    assert claimed.attempts == 1
    await repo.finish_task(claimed.id, ok=False, error="boom")
    assert claimed.status == TaskStatus.PENDING.value
    assert claimed.next_retry_at is not None
    for _ in range(claimed.max_attempts - 1):
        await repo.finish_task(claimed.id, ok=False, error="boom again")
        # 手动推进重试时间避免等待
        claimed.next_retry_at = None
        await db_session.flush()
        claimed = await repo.claim_next_task()
        assert claimed is not None
    await repo.finish_task(claimed.id, ok=False, error="final")
    assert claimed.status == TaskStatus.DEAD.value


async def test_connector_ingestion_end_to_end_idempotent(db_session):
    connector = SyntheticConnector()
    ctx = ConnectorContext(params={"seed": "42", "entities": "12", "with_history": "true"})
    stats1 = await run_connector(db_session, connector, ctx)
    assert stats1 is not None
    assert stats1.entities_created > 0
    assert stats1.statements_created > 0
    stats2 = await run_connector(db_session, connector, ctx)
    assert stats2 is None  # 幂等命中

    repo = Repository(db_session)
    _, total = await repo.search("有限公司")
    assert total > 0
    # 声明都有 connector 归属
    edges = await repo.effective_edges()
    assert all(e.predicate in {"holds_shares", "controls"} for e in edges)


async def test_document_and_evidence_chain(db_session):
    repo = Repository(db_session)
    doc = await repo.register_document(
        DocumentRef(connector_id="csv", title="样例.csv", source_url="file:///样例.csv")
    )
    snap = await repo.add_snapshot(doc.id, "ab" * 32, http_status=200, raw_stored=True)
    frag = await repo.add_fragment(
        snap.id, EvidenceRecord(field_path="row[3].ratio", raw_value="51%", normalized_value="0.51")
    )
    assert snap.content_sha256 == "ab" * 32
    assert frag.snapshot_id == snap.id


async def test_snapshot_fetched_at_explicit_and_default(db_session):
    """快照取证时间：显式传入生效；缺省走 ORM default=utcnow（向后兼容）。"""
    from datetime import UTC, datetime

    repo = Repository(db_session)
    doc = await repo.register_document(
        DocumentRef(connector_id="csv", title="t.csv", source_url="file:///t.csv")
    )
    explicit = await repo.add_snapshot(
        doc.id, "aa" * 32, fetched_at=datetime(2019, 1, 1, tzinfo=UTC)
    )
    default = await repo.add_snapshot(doc.id, "bb" * 32)
    assert explicit.fetched_at == datetime(2019, 1, 1, tzinfo=UTC)
    assert default.fetched_at is not None


async def test_staleness_rows_max_fetched_at_excludes_uncovered(db_session):
    """时效输入行：多快照取最近取证时间；无证据声明不出现；时点过滤生效。"""
    from datetime import UTC, datetime

    repo = Repository(db_session)
    a = await make_entity(repo, "P7", "王七")
    b = await make_entity(repo, "C7", "丙公司")
    doc = await repo.register_document(
        DocumentRef(connector_id="csv", title="t2.csv", source_url="file:///t2.csv")
    )
    snap_old = await repo.add_snapshot(
        doc.id, "c1" * 32, fetched_at=datetime(2010, 1, 1, tzinfo=UTC)
    )
    snap_new = await repo.add_snapshot(
        doc.id, "c2" * 32, fetched_at=datetime(2021, 6, 1, tzinfo=UTC)
    )
    frag_old = await repo.add_fragment(snap_old.id, EvidenceRecord(field_path="f", raw_value="v1"))
    frag_new = await repo.add_fragment(snap_new.id, EvidenceRecord(field_path="f", raw_value="v2"))

    def stmt(ratio: float) -> StatementRecord:
        return StatementRecord(
            subject_key="src:synthetic:P7",
            predicate=Predicate.HOLDS_SHARES,
            object_key="src:synthetic:C7",
            valid_from=date(2018, 1, 1),
            share_ratio=ratio,
            ratio_unit=RatioUnit.PERCENT,
        )

    covered, _ = await repo.add_statement(
        stmt(60.0),
        subject_id=a.id,
        object_id=b.id,
        connector_id="csv",
        ingestion_run_id=None,
        fragment_ids=[frag_old.id, frag_new.id],
    )
    bare, _ = await repo.add_statement(
        stmt(30.0), subject_id=a.id, object_id=b.id, connector_id="csv", ingestion_run_id=None
    )

    rows = {r.statement_id: r for r in await repo.evidence_staleness_rows(date(2024, 1, 1))}
    assert bare.id not in rows, "无证据声明不进时效规则"
    assert rows[covered.id].last_captured_at == datetime(2021, 6, 1).date(), "多快照取最大"

    # 时点过滤：声明 2024 年失效（valid_to）后不再出现在更晚时点
    later, _ = await repo.add_statement(
        StatementRecord(
            subject_key="src:synthetic:P7",
            predicate=Predicate.HOLDS_SHARES,
            object_key="src:synthetic:C7",
            valid_from=date(2018, 1, 1),
            valid_to=date(2023, 1, 1),
            share_ratio=20.0,
            ratio_unit=RatioUnit.PERCENT,
        ),
        subject_id=a.id,
        object_id=b.id,
        connector_id="csv",
        ingestion_run_id=None,
        fragment_ids=[frag_new.id],
    )
    rows_at = {r.statement_id for r in await repo.evidence_staleness_rows(date(2024, 1, 1))}
    assert later.id not in rows_at
    rows_before = {r.statement_id for r in await repo.evidence_staleness_rows(date(2022, 1, 1))}
    assert later.id in rows_before

    # lookup 附加 fetched_at（ISO 字符串）
    ev = await repo.evidence_for_statements([covered.id])
    assert ev[covered.id][0]["fetched_at"].startswith("20")
