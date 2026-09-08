"""connector 基类与运行上下文。

设计要点：
- fetch() 只产出纯数据记录（EntityRecord/StatementRecord/DocumentRef），
  落库统一由 ingest 阶段完成——采集与入库分离，失败可定位、可重放。
- 速率限制在 runner 层强制；connector 自身不得绕过。
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

from cg_domain.models import ConnectorSpec, DocumentRef, EntityRecord, StatementRecord


@dataclass
class IngestionIssue:
    """非致命问题：跳过的记录、缺失字段等。失败隔离到记录级。"""

    code: str
    message: str
    subject_key: str = ""


@dataclass
class ConnectorResult:
    entities: list[EntityRecord] = field(default_factory=list)
    statements: list[StatementRecord] = field(default_factory=list)
    documents: list[DocumentRef] = field(default_factory=list)
    issues: list[IngestionIssue] = field(default_factory=list)
    raw_payloads: dict[str, str] = field(default_factory=dict)  # doc_key -> 原始内容

    @property
    def content_hash(self) -> str:
        """结果内容哈希：幂等键与变更检测的基础。"""
        payload = json.dumps(
            {
                "entities": [e.model_dump(mode="json") for e in self.entities],
                "statements": [s.model_dump(mode="json") for s in self.statements],
                "documents": [d.model_dump(mode="json") for d in self.documents],
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ConnectorContext:
    """运行参数。max_records 等护栏由调用方注入，connector 必须遵守。"""

    max_records: int = 10000
    rate_limit_per_sec: float = 0.2
    store_raw_documents: bool = True
    params: dict[str, str] = field(default_factory=dict)


class BaseConnector:
    """connector 协议基类。子类实现 spec() 与 fetch()。"""

    def spec(self) -> ConnectorSpec:
        raise NotImplementedError

    def fetch(
        self, ctx: ConnectorContext
    ) -> Iterator[tuple[ConnectorResult, IngestionIssue | None]]:
        """产出 (结果批次, 问题)。问题为 None 表示批次正常。"""
        raise NotImplementedError

    def idempotency_key(self, ctx: ConnectorContext) -> str:
        """默认幂等键：connector + 参数内容哈希。参数不变 → 键不变 → 不重复导入。"""
        payload = json.dumps(
            {"connector": self.spec().connector_id, "params": ctx.params},
            sort_keys=True,
            ensure_ascii=False,
        )
        return f"{self.spec().connector_id}:{hashlib.sha256(payload.encode()).hexdigest()[:32]}"


class RateLimiter:
    """令牌间隔限速器：相邻请求间隔 ≥ 1/rate 秒。"""

    def __init__(self, rate_per_sec: float) -> None:
        self._min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last = time.monotonic()
