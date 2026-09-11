"""SQLAlchemy ORM 表定义（单一事实源 schema）。

确定性设计决策：
- 比例统一存为缩放整数（RATIO_SCALE = 1e8，即 1e8 表示 100%），避免 SQLite/PG
  浮点精度差异破坏"同输入同结果"要求；换算在 models.py 的换算函数完成。
- 时间：valid_from/valid_to 用 Date（ISO 比较）；recorded_at 用 UTC DateTime。
- 原始层表（snapshots/fragments/runs）不提供更新路径；声明修正走 supersede。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 比例缩放：1e8 = 100%。整数运算保证跨数据库确定性。
RATIO_SCALE = 10**8
# 金额缩放：存 万元×100（0.01 万元分辨率），与比例同款缩放整数策略；NULL=来源未给出
AMOUNT_SCALE = 10**2


def new_id() -> str:
    """无序 UUID 主键：避免自增 ID 泄露规模，且分布式导入不冲突。"""
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- 实体与标识


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    primary_name: Mapped[str] = mapped_column(String(512))
    primary_norm_name: Mapped[str] = mapped_column(String(512), index=True)
    merged_into_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("entities.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    note: Mapped[str] = mapped_column(Text, default="")
    # 区域（6 位行政区划代码，省级聚合并保留区县级扩展空间）与行业维度，可空；标准化层填充
    region_code: Mapped[str | None] = mapped_column(String(6), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)


class EntityIdentifier(Base):
    __tablename__ = "entity_identifiers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    # namespace: uscc / lei / ticker:<exchange> / src:<connector_id> 等，一律带命名空间
    namespace: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(128))
    valid_from: Mapped[str | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[str | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("namespace", "value", name="uq_identifier_ns_value"),
        Index("ix_identifier_entity", "entity_id", "namespace"),
    )


class NameAlias(Base):
    __tablename__ = "name_aliases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    name: Mapped[str] = mapped_column(String(512))
    norm_name: Mapped[str] = mapped_column(String(512), index=True)
    alias_type: Mapped[str] = mapped_column(String(32))
    lang: Mapped[str] = mapped_column(String(16), default="zh")
    valid_from: Mapped[str | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[str | None] = mapped_column(Date, nullable=True)


class Security(Base):
    """证券。事件/行情交换接口的锚点（本项目不做行情分析）。"""

    __tablename__ = "securities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    exchange: Mapped[str] = mapped_column(String(32))
    security_type: Mapped[str] = mapped_column(String(32), default="stock")
    valid_from: Mapped[str | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[str | None] = mapped_column(Date, nullable=True)

    __table_args__ = (UniqueConstraint("exchange", "code", name="uq_security_exchange_code"),)


# ---------------------------------------------------------------- 声明层


class Statement(Base):
    """时态关系声明（relationship statement）。

    ownership 与 control 语义分开由谓词 + 专用列约束保证：
    holds_shares 必须带 share_ratio；controls 必须带 control_type。
    专用视图 ownership_statements / control_statements 在迁移中创建。
    """

    __tablename__ = "relationship_statements"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    subject_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    predicate: Mapped[str] = mapped_column(String(48), index=True)
    object_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)

    # 比例：0..RATIO_SCALE 缩放整数；NULL 表示来源未给出（绝不编造）
    share_ratio_scaled: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    voting_ratio_scaled: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ratio_unit_original: Mapped[str | None] = mapped_column(String(16), nullable=True)
    control_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    share_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # 结构化金额（AMOUNT_SCALE 缩放整数）；amount 字符串列为来源原始记录，聚合只允许用本列
    amount_scaled: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # 时态：左闭右开 [valid_from, valid_to)；recorded_at 与有效区间分离
    valid_from: Mapped[str] = mapped_column(Date)
    valid_to: Mapped[str | None] = mapped_column(Date, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    claim_basis: Mapped[str] = mapped_column(String(16), default="normalized")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    superseded_by_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # 来源链
    connector_id: Mapped[str] = mapped_column(String(64), default="")
    ingestion_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        CheckConstraint(
            "share_ratio_scaled IS NULL OR (share_ratio_scaled >= 0 AND share_ratio_scaled <= 100000000)",
            name="ck_share_ratio_range",
        ),
        CheckConstraint(
            "voting_ratio_scaled IS NULL OR (voting_ratio_scaled >= 0 AND voting_ratio_scaled <= 100000000)",
            name="ck_voting_ratio_range",
        ),
        CheckConstraint("valid_to IS NULL OR valid_from <= valid_to", name="ck_valid_interval"),
        Index("ix_stmt_object_active", "object_id", "predicate", "status"),
        Index("ix_stmt_subject_active", "subject_id", "predicate", "status"),
        Index("ix_stmt_temporal", "valid_from", "valid_to"),
    )


class StatementEvidence(Base):
    """声明 ↔ 证据片段关联。无证据的声明只能处于 disputed/pending_review。"""

    __tablename__ = "statement_evidence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    statement_id: Mapped[str] = mapped_column(ForeignKey("relationship_statements.id"), index=True)
    evidence_fragment_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_fragments.id"), index=True
    )
    note: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------- 证据层（append-only）


class DatasetLicense(Base):
    __tablename__ = "dataset_licenses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128))
    spdx: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    allowed_use: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    connector_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    license_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notes: Mapped[str] = mapped_column(Text, default="")


class SourceSnapshot(Base):
    """抓取快照。原文可配置不落盘，但内容哈希与元数据永久保留。"""

    __tablename__ = "source_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id"), index=True)
    storage_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64))
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    raw_stored: Mapped[bool] = mapped_column(Boolean, default=False)


class EvidenceFragment(Base):
    __tablename__ = "evidence_fragments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("source_snapshots.id"), index=True)
    field_path: Mapped[str] = mapped_column(String(256), default="")
    raw_value: Mapped[str] = mapped_column(Text, default="")
    normalized_value: Mapped[str] = mapped_column(Text, default="")
    page_ref: Mapped[str] = mapped_column(String(128), default="")
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    connector_id: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    params_hash: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    counts_json: Mapped[str] = mapped_column(Text, default="{}")
    error_summary: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_run_idempotency"),)


# ---------------------------------------------------------------- 实体解析


class ResolutionCandidate(Base):
    __tablename__ = "resolution_candidates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    entity_id_left: Mapped[str] = mapped_column(String(32), index=True)
    entity_id_right: Mapped[str] = mapped_column(String(32), index=True)
    features_json: Mapped[str] = mapped_column(Text, default="{}")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    threshold: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(64), default="")
    method_version: Mapped[str] = mapped_column(String(32), default="")
    input_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResolutionDecision(Base):
    __tablename__ = "resolution_decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("resolution_candidates.id"), index=True)
    decision: Mapped[str] = mapped_column(String(16))
    decided_by: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(64), default="")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- 派生层（可重算）


class OwnershipCalculation(Base):
    """一次穿透/聚合计算的登记：输入版本、算法版本、配置哈希，保证可复现。"""

    __tablename__ = "ownership_calculations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    root_entity_id: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(8))  # up / down
    at_date: Mapped[str] = mapped_column(Date)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    config_hash: Mapped[str] = mapped_column(String(64))
    algorithm_version: Mapped[str] = mapped_column(String(32))
    inputs_hash: Mapped[str] = mapped_column(String(64), default="")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    unknowns_json: Mapped[str] = mapped_column(Text, default="[]")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DerivedPath(Base):
    __tablename__ = "derived_paths"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    calculation_id: Mapped[str] = mapped_column(ForeignKey("ownership_calculations.id"), index=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    path_json: Mapped[str] = mapped_column(Text, default="[]")
    direct_ratio_scaled: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    path_product_scaled: Mapped[int] = mapped_column(BigInteger, default=0)
    cycle_involved: Mapped[bool] = mapped_column(Boolean, default=False)


class RiskFlag(Base):
    __tablename__ = "risk_flags"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    flag_type: Mapped[str] = mapped_column(String(48), index=True)
    subject_entity_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subject_statement_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    calculation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- 质量与复核


class QualityIssue(Base):
    __tablename__ = "quality_issues"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    rule_name: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    entity_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    statement_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="open")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewItem(Base):
    __tablename__ = "review_queue"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(48), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="open")
    assignee: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------- 运营与安全


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """追加式审计日志。代码中不提供 update/delete 路径。"""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128), default="")
    request_id: Mapped[str] = mapped_column(String(64), default="")
    result: Mapped[str] = mapped_column(String(16))
    detail_json: Mapped[str] = mapped_column(Text, default="{}")


class Task(Base):
    """worker 任务。幂等键唯一，指数退避，失败隔离在任务级。"""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(48), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


ALL_TABLES: list[type[Base]] = [
    Entity,
    EntityIdentifier,
    NameAlias,
    Security,
    Statement,
    StatementEvidence,
    DatasetLicense,
    SourceDocument,
    SourceSnapshot,
    EvidenceFragment,
    IngestionRun,
    ResolutionCandidate,
    ResolutionDecision,
    OwnershipCalculation,
    DerivedPath,
    RiskFlag,
    QualityIssue,
    ReviewItem,
    User,
    AuditLog,
    Task,
]


def metadata_any() -> Any:
    return Base.metadata
