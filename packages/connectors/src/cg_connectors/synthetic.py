"""合成数据连接器：确定性生成虚构中国企业网络用于演示与测试。

合规声明：所有名称、代码、比例均为随机生成，不指向真实主体；
USCC 使用 GB 32100 校验位算法但号段为保留测试号段（93 开头非真实分配）。
相同 seed 必然产出相同记录（可复现）。
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import date
from typing import Any

from cg_domain.enums import ClaimBasis, ControlType, EntityKind, Predicate, RatioUnit
from cg_domain.models import (
    ConnectorSpec,
    DocumentRef,
    EntityRecord,
    EvidenceRecord,
    StatementRecord,
)
from cg_domain.normalization import is_valid_uscc
from cg_domain.regions import INDUSTRIES, PROVINCES

from cg_connectors.base import (
    BaseConnector,
    ConnectorContext,
    ConnectorResult,
    IngestionIssue,
)

_SURNAMES = "王李张刘陈杨黄赵周吴徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭"
_GIVEN = "伟芳娜敏静磊军洋勇艳杰娟涛明超秀兰霞平刚桂华建文军鑫宇晨曦致远"
_PREFIX = "华康泰安瑞恒鑫源宏远中恒嘉诚汇金天启鼎盛永信博衍知行澄明"
_MIDDLE = "科技贸易实业投资控股信息技术新材料智能制造生物医药咨询服务"
_CITY = "北京上海深圳广州杭州成都武汉南京西安重庆苏州天津"
_SUFFIX = ("有限公司", "股份有限公司")

_BATCH = 400

# 省份抽样权重：沿海/经济活跃省份更高，形成有结构的（而非均匀噪声的）跨区域流动演示
_REGION_WEIGHTS = tuple(
    8 if code in ("110000", "310000", "440000", "330000", "320000", "500000") else 3
    for code, _, _ in PROVINCES
)


def _registered_capital_wan(rng: random.Random) -> float:
    """虚构注册资本（万元）：对数均匀分布，覆盖小微企业到大型企业量级。"""
    return round(10 ** rng.uniform(2.0, 5.7), 2)


def _fake_uscc(rng: random.Random) -> str:
    """生成通过 GB 32100 校验位验证的合成代码（93 测试号段）。"""
    base = "93" + "".join(rng.choice("0123456789") for _ in range(15))
    return _uscc_with_check(base)


def _uscc_with_check(base17: str) -> str:
    charset = "0123456789ABCDEFGHJKLMNPQRTUWXY"
    weights = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)
    total = sum(charset.index(ch) * w for ch, w in zip(base17, weights, strict=True))
    return base17 + charset[(31 - total % 31) % 31]


class SyntheticConnector(BaseConnector):
    """参数：entities（主体总数）、seed、with_history（是否生成历史变更）。"""

    def spec(self) -> ConnectorSpec:
        return ConnectorSpec(
            connector_id="synthetic",
            description="确定性合成演示数据（虚构主体，仅用于本地演示与测试）",
            allowed_use="synthetic-demo",
            license_name="CC0-1.0",
            respects_robots=True,
            touches_auth_boundary=False,
            rate_limit_per_sec=1000.0,  # 本地生成无网络请求
            stores_raw_documents=True,
            enabled_by_default=True,
        )

    def idempotency_key(self, ctx: ConnectorContext) -> str:
        return (
            "synthetic:"
            + str(ctx.params.get("seed", "42"))
            + ":"
            + str(ctx.params.get("entities", "40"))
        )

    def fetch(
        self, ctx: ConnectorContext
    ) -> Iterator[tuple[ConnectorResult, IngestionIssue | None]]:
        rng = random.Random(int(ctx.params.get("seed", "42")))  # nosec B311 演示数据生成，非安全用途
        n_entities = min(int(ctx.params.get("entities", "40")), ctx.max_records)
        with_history = ctx.params.get("with_history", "true") == "true"

        graph = self._build_graph(rng, n_entities, with_history)
        entities = graph["entities"]
        statements = graph["statements"]

        doc = DocumentRef(
            connector_id="synthetic",
            title="合成演示数据（虚构）",
            source_url="internal://synthetic",
            license_name="CC0-1.0",
            notes="由 SyntheticConnector 本地生成，无外部网络访问",
        )

        for start in range(0, len(entities), _BATCH):
            batch_entities = entities[start : start + _BATCH]
            batch_stmts = statements[start : start + _BATCH]
            result = ConnectorResult(
                entities=batch_entities,
                statements=batch_stmts,
                documents=[doc],
            )
            result.raw_payloads["synthetic-snapshot"] = json_dumps(graph, start)
            yield result, None

    # ------------------------------------------------------------------

    def _build_graph(
        self, rng: random.Random, n_entities: int, with_history: bool
    ) -> dict[str, Any]:
        entities: list[EntityRecord] = []
        statements: list[StatementRecord] = []

        n_companies = max(n_entities * 2 // 3, 4)
        n_persons = max(n_entities - n_companies, 2)

        # 虚构企业
        used_names: set[str] = set()
        companies: list[EntityRecord] = []
        for i in range(n_companies):
            while True:
                name = (
                    rng.choice(_PREFIX)
                    + rng.choice(_PREFIX)
                    + rng.choice(_MIDDLE)
                    + rng.choice(_CITY)
                    + rng.choice(_SUFFIX)
                )
                if name not in used_names:
                    used_names.add(name)
                    break
            uscc = _fake_uscc(rng)
            kind = EntityKind.LISTED_COMPANY if i < 3 else EntityKind.COMPANY
            province = rng.choices(PROVINCES, weights=_REGION_WEIGHTS, k=1)[0]
            record = EntityRecord(
                connector_id="synthetic",
                external_id=f"C{i:04d}",
                kind=kind,
                name=name,
                uscc=uscc,
                ticker=f"{600000 + i * 7:06d}" if kind is EntityKind.LISTED_COMPANY else None,
                exchange="SSE" if kind is EntityKind.LISTED_COMPANY else None,
                region_code=province[0],
                industry=rng.choice(INDUSTRIES),
            )
            if not is_valid_uscc(uscc):  # 生成器不变量：确定性种子也不得产出非法 USCC
                raise ValueError(f"synthetic generator produced invalid USCC: {uscc}")
            companies.append(record)
        entities.extend(companies)

        # 虚构自然人
        persons: list[EntityRecord] = []
        for i in range(n_persons):
            name = rng.choice(_SURNAMES) + rng.choice(_GIVEN) + rng.choice(_GIVEN)
            province = rng.choices(PROVINCES, weights=_REGION_WEIGHTS, k=1)[0]
            persons.append(
                EntityRecord(
                    connector_id="synthetic",
                    external_id=f"P{i:04d}",
                    kind=EntityKind.PERSON,
                    name=name,
                    region_code=province[0],
                )
            )
        entities.extend(persons)

        def evidence(path: str, raw: str) -> list[EvidenceRecord]:
            return [
                EvidenceRecord(
                    document_title="合成演示数据（虚构）",
                    source_url="internal://synthetic",
                    field_path=path,
                    raw_value=raw,
                    normalized_value=raw,
                    page_ref="synthetic",
                )
            ]

        base_date = date(2018, 1, 1)
        # 每家公司 1-5 名股东；约一半公司含自然人 UBO（≥25%）
        for idx, company in enumerate(companies):
            n_holders = rng.randint(1, min(5, len(persons)))
            holders = rng.sample(persons, n_holders)
            remaining = 95.0
            for j, holder in enumerate(holders):
                if j == len(holders) - 1:
                    ratio = round(rng.uniform(10.0, max(11.0, remaining)), 2)
                else:
                    ratio = round(rng.uniform(5.0, remaining * 0.6), 2)
                remaining -= ratio
                statements.append(
                    StatementRecord(
                        subject_key=holder.key,
                        predicate=Predicate.HOLDS_SHARES,
                        object_key=company.key,
                        valid_from=base_date,
                        share_ratio=ratio,
                        ratio_unit=RatioUnit.PERCENT,
                        amount_wan=_registered_capital_wan(rng),
                        confidence=1.0,
                        claim_basis=ClaimBasis.NORMALIZED,
                        evidence=evidence(f"shareholders[{idx}][{j}].ratio", f"{ratio:.2f}%"),
                    )
                )
                if ratio >= 34.0:
                    statements.append(
                        StatementRecord(
                            subject_key=holder.key,
                            predicate=Predicate.CONTROLS,
                            object_key=company.key,
                            valid_from=base_date,
                            control_type=ControlType.VOTING_RIGHTS,
                            voting_ratio=ratio,
                            ratio_unit=RatioUnit.PERCENT,
                            evidence=evidence(f"shareholders[{idx}][{j}].control", "控制"),
                        )
                    )

        # 公司间持股链（穿透演示）：上游公司持有多家下游
        for i in range(2, len(companies)):
            parent = companies[rng.randrange(max(1, i // 2))]
            if parent is companies[i]:
                continue
            ratio = round(rng.uniform(51.0, 90.0), 2)
            statements.append(
                StatementRecord(
                    subject_key=parent.key,
                    predicate=Predicate.HOLDS_SHARES,
                    object_key=companies[i].key,
                    valid_from=base_date,
                    share_ratio=ratio,
                    ratio_unit=RatioUnit.PERCENT,
                    amount_wan=_registered_capital_wan(rng),
                    evidence=evidence(f"equity[{i}].ratio", f"{ratio:.2f}%"),
                )
            )

        # 故意构造交叉持股环：C0 ↔ C1（环路/交叉持股检测演示）
        if len(companies) >= 2:
            statements.append(
                StatementRecord(
                    subject_key=companies[0].key,
                    predicate=Predicate.HOLDS_SHARES,
                    object_key=companies[1].key,
                    valid_from=base_date,
                    share_ratio=30.0,
                    ratio_unit=RatioUnit.PERCENT,
                    evidence=evidence("cycle[0]", "30.00%"),
                )
            )
            statements.append(
                StatementRecord(
                    subject_key=companies[1].key,
                    predicate=Predicate.HOLDS_SHARES,
                    object_key=companies[0].key,
                    valid_from=base_date,
                    share_ratio=25.0,
                    ratio_unit=RatioUnit.PERCENT,
                    evidence=evidence("cycle[1]", "25.00%"),
                )
            )

        # 历史变更演示：某公司股东变更（时间点查询演示）
        if with_history and persons:
            target = companies[-1]
            transfer_date = date(2022, 6, 1)
            statements.append(
                StatementRecord(
                    subject_key=persons[0].key,
                    predicate=Predicate.HOLDS_SHARES,
                    object_key=target.key,
                    valid_from=base_date,
                    valid_to=transfer_date,  # 左闭右开：变更日当天起旧声明失效
                    share_ratio=60.0,
                    ratio_unit=RatioUnit.PERCENT,
                    evidence=evidence("history[0].before", "60.00%（至 2022-05-31）"),
                )
            )
            statements.append(
                StatementRecord(
                    subject_key=persons[1 % len(persons)].key,
                    predicate=Predicate.HOLDS_SHARES,
                    object_key=target.key,
                    valid_from=transfer_date,
                    share_ratio=60.0,
                    ratio_unit=RatioUnit.PERCENT,
                    evidence=evidence("history[0].after", "60.00%（自 2022-06-01）"),
                )
            )

        return {"entities": entities, "statements": statements, "documents": []}


def json_dumps(graph: dict[str, Any], start: int) -> str:
    import json

    return json.dumps(
        {"batch_start": start, "count": len(graph["entities"])},
        ensure_ascii=False,
    )
