"""CapitalGraph CN 领域模型包。

包含实体/标识/别名的类型与 ORM、时态声明（relationship statements）、
证据与来源链条、实体解析决策记录与派生结果存储。

分层约束（见 DATA_MODEL.md）：
- 原始层只追加（sources/snapshots/fragments/runs）
- 标准化层版本化修正（statements 用 status + superseded_by_id）
- 发布层可重算（derived_*，带算法版本与配置哈希）
"""

from cg_domain.config import Settings, load_settings
from cg_domain.db import make_engine, make_session_factory
from cg_domain.enums import (
    AliasType,
    ClaimBasis,
    ControlType,
    DecisionBy,
    DecisionOutcome,
    EntityKind,
    FlagType,
    IngestionStatus,
    Predicate,
    RatioUnit,
    ReviewKind,
    ReviewStatus,
    Role,
    StatementStatus,
    TaskStatus,
)
from cg_domain.errors import DomainError, RatioError, TemporalError, ValidationError
from cg_domain.models import (
    ConnectorSpec,
    DocumentRef,
    EntityRecord,
    EvidenceRecord,
    PenetrationConfig,
    StatementRecord,
)
from cg_domain.normalization import is_valid_uscc, normalize_company_name, normalize_name
from cg_domain.orm import RATIO_SCALE

__all__ = [
    "AliasType",
    "ClaimBasis",
    "ConnectorSpec",
    "ControlType",
    "DecisionBy",
    "DecisionOutcome",
    "DomainError",
    "DocumentRef",
    "EntityKind",
    "EntityRecord",
    "EvidenceRecord",
    "FlagType",
    "IngestionStatus",
    "PenetrationConfig",
    "Predicate",
    "RATIO_SCALE",
    "RatioError",
    "RatioUnit",
    "ReviewKind",
    "ReviewStatus",
    "Role",
    "Settings",
    "StatementRecord",
    "StatementStatus",
    "TaskStatus",
    "TemporalError",
    "ValidationError",
    "is_valid_uscc",
    "load_settings",
    "make_engine",
    "make_session_factory",
    "normalize_company_name",
    "normalize_name",
]
