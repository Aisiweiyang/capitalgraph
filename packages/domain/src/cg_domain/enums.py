"""领域枚举。所有状态机取值集中在此，避免魔法字符串散落各层。"""

from enum import StrEnum


class EntityKind(StrEnum):
    """主体类型。政府/国资机构单列，因其控制语义（行政控制）与股权控制不同。"""

    COMPANY = "company"
    LISTED_COMPANY = "listed_company"
    PERSON = "person"
    FUND = "fund"
    PARTNERSHIP = "partnership"
    INVESTOR = "investor"
    GOVERNMENT_BODY = "government_body"
    SECURITY = "security"
    BRANCH = "branch"


class Predicate(StrEnum):
    """声明谓词。持股与控制严格分开（ownership ≠ control）。"""

    HOLDS_SHARES = "holds_shares"
    CONTROLS = "controls"
    BENEFICIAL_OWNER_CANDIDATE = "beneficial_owner_candidate"
    INVESTS_IN = "invests_in"
    APPOINTED_AT = "appointed_at"
    LEGAL_REPRESENTATIVE = "legal_representative"
    PROVIDES_GUARANTEE = "provides_guarantee"
    PLEDGES_SHARES = "pledges_shares"
    RELATED_TRANSACTION = "related_transaction"
    SAME_CONTROL = "same_control"


class StatementStatus(StrEnum):
    """声明生命周期。修正不覆盖：旧声明转 superseded 并指向新声明。"""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
    DISPUTED = "disputed"
    PENDING_REVIEW = "pending_review"


class ClaimBasis(StrEnum):
    """事实等级：原始事实 / 标准化事实 / 算法推断 / 人工判断。"""

    RAW = "raw"
    NORMALIZED = "normalized"
    INFERRED = "inferred"
    MANUAL = "manual"


class ControlType(StrEnum):
    """控制类型。政府控制为行政控制，与股权控制并存时需人工判断。"""

    VOTING_RIGHTS = "voting_rights"
    BOARD_CONTROL = "board_control"
    CONTRACT = "contract"
    DE_FACTO = "de_facto"
    GOVERNMENT = "government"


class RatioUnit(StrEnum):
    """来源比例单位。入库统一换算为 0-1 分数（整数缩放存储）。"""

    PERCENT = "percent"
    FRACTION = "fraction"


class AliasType(StrEnum):
    OFFICIAL = "official"
    FORMER = "former"
    ABBREVIATION = "abbreviation"
    TRANSLATION = "translation"


class Role(StrEnum):
    """RBAC 角色。admin > analyst > viewer，后端强制，默认拒绝。"""

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class DecisionOutcome(StrEnum):
    MERGE = "merge"
    REJECT = "reject"
    PENDING = "pending"


class DecisionBy(StrEnum):
    RULE = "rule"
    MODEL = "model"
    HUMAN = "human"


class FlagType(StrEnum):
    CYCLE = "cycle"
    CROSS_HOLDING = "cross_holding"
    MISSING_RATIO = "missing_ratio"
    RATIO_ANOMALY = "ratio_anomaly"
    LOW_CONFIDENCE = "low_confidence"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    STALE_SOURCE = "stale_source"
    CONFLICTING_STATEMENTS = "conflicting_statements"
    # v0.4 担保/质押风险传导（算法候选，见 ADR-016）
    GUARANTEE_CYCLE = "guarantee_cycle"
    GUARANTEE_CHAIN_EXPOSURE = "guarantee_chain_exposure"


class ReviewKind(StrEnum):
    CONFLICT = "conflict"
    SUSPECTED_DUPLICATE = "suspected_duplicate"
    LOW_CONFIDENCE_MATCH = "low_confidence_match"
    STALE_SOURCE = "stale_source"


class ReviewStatus(StrEnum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"


class IngestionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"
