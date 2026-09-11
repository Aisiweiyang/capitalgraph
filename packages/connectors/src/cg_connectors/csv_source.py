"""CSV fixture 连接器：面向测试与用户自备公开数据的受控导入。

schema contract（15 个必需表头 + 若干可选列；多余列忽略）：
必需：record_type,subject_id,subject_name,subject_uscc,predicate,object_id,object_name,object_uscc,
     ratio,ratio_unit,valid_from,valid_to,evidence_url,field_path,raw_value
可选：region_code（6 位省级行政区划代码）、industry（行业名）、amount_wan（金额，万元）
     ——entity 行与关系行均可携带；关系行自动补建实体时同样继承。

- record_type ∈ {entity, holding, control}
- 坏行跳过并记录 IngestionIssue（失败隔离），不中断整批。
- 可选列给出但非法（如 region_code 不是省级行政区划代码）→ 该行拒绝并留痕，与坏行同策略。
- 文件大小上限由 runner 校验（zip bomb / 巨型文件防护在 runner 层）。
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from cg_domain.enums import ClaimBasis, ControlType, EntityKind, Predicate, RatioUnit
from cg_domain.errors import DomainError
from cg_domain.models import (
    ConnectorSpec,
    DocumentRef,
    EntityRecord,
    EvidenceRecord,
    StatementRecord,
)
from cg_domain.regions import is_province_code

from cg_connectors.base import (
    BaseConnector,
    ConnectorContext,
    ConnectorResult,
    IngestionIssue,
)

_REQUIRED_HEADERS = [
    "record_type",
    "subject_id",
    "subject_name",
    "subject_uscc",
    "predicate",
    "object_id",
    "object_name",
    "object_uscc",
    "ratio",
    "ratio_unit",
    "valid_from",
    "valid_to",
    "evidence_url",
    "field_path",
    "raw_value",
]

_PREDICATE_MAP = {
    "holding": Predicate.HOLDS_SHARES,
    "control": Predicate.CONTROLS,
}


class CsvFixtureConnector(BaseConnector):
    """参数：path（CSV 文件路径）。编码 UTF-8（含 BOM 容忍）。"""

    def spec(self) -> ConnectorSpec:
        return ConnectorSpec(
            connector_id="csv",
            description="本地 CSV fixture 导入（用户提供数据，需自证授权）",
            allowed_use="user-provided",
            license_name="user-provided",
            respects_robots=True,
            touches_auth_boundary=False,
            rate_limit_per_sec=1000.0,
            stores_raw_documents=True,
            enabled_by_default=True,
        )

    def fetch(
        self, ctx: ConnectorContext
    ) -> Iterator[tuple[ConnectorResult, IngestionIssue | None]]:
        path_raw = ctx.params.get("path", "")
        # 统一转绝对路径：相对路径会让 as_uri() 抛错，且相对基准依赖进程工作目录不可靠
        path = Path(path_raw).resolve()
        if not path.is_file():
            yield (
                ConnectorResult(),
                IngestionIssue(code="file_not_found", message=f"CSV 不存在: {path.name}"),
            )
            return
        size = path.stat().st_size
        if size > 32 * 1024 * 1024:
            yield (
                ConnectorResult(),
                IngestionIssue(code="file_too_large", message="CSV 超过 32MB 上限"),
            )
            return

        text = path.read_text(encoding="utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        missing = [h for h in _REQUIRED_HEADERS if h not in headers]
        if missing:
            yield (
                ConnectorResult(),
                IngestionIssue(
                    code="schema_mismatch",
                    message=f"缺少必需列: {','.join(missing)}",
                ),
            )
            return

        result = ConnectorResult(
            documents=[
                DocumentRef(
                    connector_id="csv",
                    title=path.name,
                    source_url=path.as_uri(),
                    license_name="user-provided",
                )
            ]
        )
        result.raw_payloads[path.name] = text[:100000]
        seen_entities: set[str] = set()
        issues: list[IngestionIssue] = []

        for line_no, row in enumerate(reader, start=2):
            record_type = (row.get("record_type") or "").strip().lower()
            try:
                if record_type == "entity":
                    entity = self._entity_row(row)
                    result.entities.append(entity)
                    seen_entities.add(entity.external_id)
                    continue
                statement = self._statement_row(row)
                result.statements.append(statement)
                for side in ("subject", "object"):
                    name = (row.get(f"{side}_name") or "").strip()
                    ext_id = (row.get(f"{side}_id") or "").strip()
                    uscc = (row.get(f"{side}_uscc") or "").strip() or None
                    if ext_id and ext_id not in seen_entities:
                        result.entities.append(
                            EntityRecord(
                                connector_id="csv",
                                external_id=ext_id,
                                kind=EntityKind.PERSON
                                if ext_id.upper().startswith("P")
                                else EntityKind.COMPANY,
                                name=name or ext_id,
                                uscc=uscc,
                            )
                        )
                        seen_entities.add(ext_id)
            except (DomainError, ValueError, TypeError) as exc:
                # 坏行隔离：字段错位/比例非法/日期非法都只丢弃该行并留痕
                issues.append(
                    IngestionIssue(
                        code="row_rejected",
                        message=f"第 {line_no} 行: {exc}",
                        subject_key=(row.get("subject_id") or ""),
                    )
                )
                continue
            if len(result.entities) + len(result.statements) >= ctx.max_records:
                issues.append(IngestionIssue(code="max_records", message="达到记录上限，提前停止"))
                break

        yield result, (issues[0] if issues else None)
        for issue in issues[1:]:
            yield ConnectorResult(), issue

    def _entity_row(self, row: dict[str, str]) -> EntityRecord:
        ext_id = (row.get("subject_id") or "").strip()
        name = (row.get("subject_name") or "").strip()
        if not ext_id or not name:
            raise DomainError("entity 行缺少 subject_id 或 subject_name")
        return EntityRecord(
            connector_id="csv",
            external_id=ext_id,
            kind=EntityKind.PERSON if ext_id.upper().startswith("P") else EntityKind.COMPANY,
            name=name,
            uscc=(row.get("subject_uscc") or "").strip() or None,
            region_code=self._region(row),
            industry=(row.get("industry") or "").strip() or None,
        )

    def _region(self, row: dict[str, str]) -> str | None:
        """可选列 region_code：给出则必须是省级行政区划代码，否则拒绝该行。"""
        code = (row.get("region_code") or "").strip() or None
        if code is not None and not is_province_code(code):
            raise DomainError(f"region_code 非省级行政区划代码: {code}")
        return code

    def _statement_row(self, row: dict[str, str]) -> StatementRecord:
        record_type = (row.get("record_type") or "").strip().lower()
        predicate = _PREDICATE_MAP.get(record_type)
        if predicate is None:
            raise DomainError(f"未知 record_type: {record_type}")
        self._region(row)  # 可选维度列给出即校验，坏值拒绝该行
        ratio_raw = (row.get("ratio") or "").strip()
        ratio = float(ratio_raw) if ratio_raw else None
        unit_raw = (row.get("ratio_unit") or "percent").strip().lower()
        unit = RatioUnit.FRACTION if unit_raw == "fraction" else RatioUnit.PERCENT
        valid_from_raw = (row.get("valid_from") or "").strip()
        valid_from = date.fromisoformat(valid_from_raw) if valid_from_raw else date.today()
        valid_to_raw = (row.get("valid_to") or "").strip()
        valid_to = date.fromisoformat(valid_to_raw) if valid_to_raw else None
        ev = EvidenceRecord(
            document_title="csv-fixture",
            source_url=(row.get("evidence_url") or "").strip(),
            field_path=(row.get("field_path") or "").strip(),
            raw_value=(row.get("raw_value") or "").strip(),
            normalized_value=(row.get("raw_value") or "").strip(),
        )
        amount_raw = (row.get("amount_wan") or "").strip()
        try:
            amount_wan = float(amount_raw) if amount_raw else None
        except ValueError:
            raise DomainError(f"amount_wan 不是数字: {amount_raw}") from None
        return StatementRecord(
            subject_key=f"src:csv:{(row.get('subject_id') or '').strip()}",
            predicate=predicate,
            object_key=f"src:csv:{(row.get('object_id') or '').strip()}",
            valid_from=valid_from,
            valid_to=valid_to,
            share_ratio=ratio,
            ratio_unit=unit,
            amount_wan=amount_wan,
            control_type=ControlType.VOTING_RIGHTS if predicate is Predicate.CONTROLS else None,
            claim_basis=ClaimBasis.NORMALIZED,
            evidence=[ev],
        )
