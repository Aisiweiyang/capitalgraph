"""跨包契约模型（Pydantic）与比例换算。

这些模型是 connector → 领域层 的唯一数据入口：connector 产出
EntityRecord / StatementRecord / DocumentRef / EvidenceRecord，
由入库服务负责实体解析、证据链落库与时态 supersede。

比例约定：来源可能给百分数（51.00）或分数（0.51），必须显式带单位；
换算函数返回 0..RATIO_SCALE 的缩放整数，杜绝浮点进入存储层。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cg_domain.enums import ClaimBasis, ControlType, EntityKind, Predicate, RatioUnit
from cg_domain.errors import RatioError, ValidationError
from cg_domain.normalization import normalize_name
from cg_domain.orm import AMOUNT_SCALE, RATIO_SCALE

EntityKeyNamespace = Literal["uscc", "lei", "ticker", "src"]
# 实体外部键：namespace:value，例如 "uscc:91110000XXXXXXXXXX" / "src:synthetic:E001"
EntityKey = str


def ratio_to_scaled(value: float, unit: RatioUnit) -> int:
    """来源比例 → 缩放整数。越界即拒绝（宁可缺数不可错数）。"""
    if value != value:  # NaN
        raise RatioError("比例不能为 NaN")
    fraction = value / 100.0 if unit is RatioUnit.PERCENT else value
    if fraction < 0.0 or fraction > 1.0:
        raise RatioError(f"比例越界: {value} ({unit.value})，换算后须在 0..1")
    scaled = round(fraction * RATIO_SCALE)
    return scaled


def scaled_to_percent(scaled: int | None) -> float | None:
    """缩放整数 → 百分数（保留 6 位小数）。None 表示来源未给出，保持 unknown。"""
    if scaled is None:
        return None
    return round(scaled * 100.0 / RATIO_SCALE, 6)


class EntityRecord(BaseModel):
    """connector 产出的主体记录。external_id 由 connector 保证在其数据源内稳定。"""

    model_config = ConfigDict(frozen=True)

    connector_id: str
    external_id: str
    kind: EntityKind = EntityKind.COMPANY
    name: str = Field(min_length=1, max_length=512)
    former_names: list[str] = Field(default_factory=list)
    uscc: str | None = None
    lei: str | None = None
    ticker: str | None = None
    exchange: str | None = None
    valid_from: date | None = None
    region_code: str | None = None
    industry: str | None = None

    @property
    def norm_name(self) -> str:
        return normalize_name(self.name)

    @property
    def key(self) -> EntityKey:
        return f"src:{self.connector_id}:{self.external_id}"


class EvidenceRecord(BaseModel):
    """单条声明对应的证据片段。connector 必须给出 raw 值与字段路径。"""

    model_config = ConfigDict(frozen=True)

    document_title: str = ""
    source_url: str = ""
    field_path: str = ""
    raw_value: str = ""
    normalized_value: str = ""
    page_ref: str = ""
    content_sha256: str = ""  # 快照内容哈希；为空时由入库服务计算
    captured_at: datetime | None = None  # 快照取证时间；缺省由入库时间兜底（向后兼容）


class StatementRecord(BaseModel):
    """关系声明记录。时态区间左闭右开。"""

    model_config = ConfigDict(frozen=True)

    subject_key: EntityKey
    predicate: Predicate
    object_key: EntityKey
    valid_from: date
    valid_to: date | None = None
    recorded_at: datetime | None = None

    share_ratio: float | None = None
    voting_ratio: float | None = None
    ratio_unit: RatioUnit = RatioUnit.PERCENT
    control_type: ControlType | None = None
    share_class: str | None = None
    amount: str | None = None
    currency: str | None = None
    amount_wan: float | None = Field(default=None, ge=0.0)

    claim_basis: ClaimBasis = ClaimBasis.NORMALIZED
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    note: str = ""
    evidence: list[EvidenceRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> StatementRecord:
        if self.valid_to is not None and self.valid_from > self.valid_to:
            raise ValidationError(f"时间区间倒置: {self.valid_from} > {self.valid_to}")
        if self.predicate is Predicate.HOLDS_SHARES and self.share_ratio is None:
            raise RatioError("holds_shares 声明必须给出持股比例；确实缺失时请在来源标注")
        if self.predicate is Predicate.CONTROLS and self.control_type is None:
            raise ValidationError("controls 声明必须给出 control_type")
        # 构造期即换算并校验比例范围（越界直接拒绝，宁可缺数不可错数）
        if self.share_ratio is not None:
            ratio_to_scaled(self.share_ratio, self.ratio_unit)
        if self.voting_ratio is not None:
            ratio_to_scaled(self.voting_ratio, self.ratio_unit)
        if self.amount_wan is not None and self.amount_wan != self.amount_wan:
            raise ValidationError("金额不能为 NaN")
        return self

    @property
    def amount_scaled(self) -> int | None:
        """万元 → 万元×100 缩放整数。None 表示来源未给出，保持 unknown。"""
        if self.amount_wan is None:
            return None
        return round(self.amount_wan * AMOUNT_SCALE)

    @property
    def share_ratio_scaled(self) -> int | None:
        if self.share_ratio is None:
            return None
        return ratio_to_scaled(self.share_ratio, self.ratio_unit)

    @property
    def voting_ratio_scaled(self) -> int | None:
        if self.voting_ratio is None:
            return None
        return ratio_to_scaled(self.voting_ratio, self.ratio_unit)


class DocumentRef(BaseModel):
    """来源文档登记。"""

    model_config = ConfigDict(frozen=True)

    connector_id: str
    title: str = ""
    source_url: str = ""
    license_name: str = ""
    notes: str = ""


class ConnectorSpec(BaseModel):
    """connector 合规声明（DATA_GOVERNANCE 清单的字段化）。缺省即最保守。"""

    model_config = ConfigDict(frozen=True)

    connector_id: str
    description: str = ""
    allowed_use: str = "internal-research"
    license_name: str = "synthetic"
    respects_robots: bool = True
    touches_auth_boundary: bool = False
    rate_limit_per_sec: float = 0.2
    stores_raw_documents: bool = True
    enabled_by_default: bool = False


class PenetrationConfig(BaseModel):
    """穿透算法配置。全字段有界，超过服务端硬上限的请求被拒。"""

    model_config = ConfigDict(frozen=True)

    at: date | None = None
    direction: Literal["up", "down"] = "up"
    max_depth: int = Field(default=6, ge=1, le=12)
    min_ratio_percent: float = Field(default=0.01, ge=0.0, le=100.0)
    max_paths: int = Field(default=5000, ge=1, le=100000)
    max_nodes: int = Field(default=20000, ge=1, le=1000000)
    timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)
    include_missing_ratio: bool = False  # 缺比例的边是否参与路径（参与则结果标 unknown）
    focus_entity_id: str | None = None  # 路径高亮目标

    def canonical_json(self) -> str:
        """配置规范化序列化（字段排序），供哈希复现。"""
        import json

        return json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
