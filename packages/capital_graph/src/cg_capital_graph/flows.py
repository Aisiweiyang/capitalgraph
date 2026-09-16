"""跨区域资本流动聚合（纯函数、确定性、无 IO）。

口径（ADR-014，全部可追溯到时态声明）：
- 输入边为某时点 status=active 且时点有效的持股/投资声明（时点过滤由仓储完成）；
- 跨区域流动 = from_region != to_region；同省边只计入省内内部边计数，不进流向；
- 省份未知（region_code 为空）的边不进聚合，以 unknown_region_edges 显式计数；
- 金额口径 = amount_scaled 求和（万元）；缺失金额的边计入边数与 amount_missing_edges，
  不计入金额合计，绝不补值；
- 比例口径 = share_ratio_scaled 求和（百分数）；缺失比例边计入 ratio_missing_edges；
- HHI = 各省流出金额份额（百分点）平方和，范围 0..10000；流出总额为 0 时输出 None。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

AMOUNT_WAN_PER_SCALED = 0.01  # amount_scaled(万元×100) → 万元


@dataclass(frozen=True)
class FlowEdge:
    """流动聚合输入边。时点有效性由仓储过滤，本层不做时间判断。"""

    statement_id: str
    from_region: str
    to_region: str
    object_id: str  # 标的实体，用于行业维度的二次聚合
    ratio_scaled: int | None
    amount_scaled: int | None
    year: int
    subject_id: str | None = None  # 出资方实体；族间流向聚合（families.family_flows）需要


@dataclass(frozen=True)
class RegionFlow:
    """一条省→省流向的聚合结果。"""

    from_region: str
    to_region: str
    edge_count: int
    amount_edges: int
    amount_wan: float | None
    total_share_percent: float | None
    ratio_missing_edges: int


def cross_region(edges: list[FlowEdge]) -> list[FlowEdge]:
    """只保留跨省边；同省边不构成区域间流动。"""
    return [e for e in edges if e.from_region != e.to_region]


def aggregate_flows(
    edges: list[FlowEdge],
    *,
    min_amount_wan: float | None = None,
    limit: int | None = None,
) -> list[RegionFlow]:
    """聚合省→省流向。min_amount_wan 只过滤"有金额且合计低于阈值"的流向。"""
    buckets: dict[tuple[str, str], list[FlowEdge]] = defaultdict(list)
    for e in cross_region(edges):
        buckets[(e.from_region, e.to_region)].append(e)

    flows: list[RegionFlow] = []
    for (src, dst), group in buckets.items():
        amount_scaleds = [e.amount_scaled for e in group if e.amount_scaled is not None]
        ratios = [e.ratio_scaled for e in group if e.ratio_scaled is not None]
        amount_wan = (
            round(sum(amount_scaleds) * AMOUNT_WAN_PER_SCALED, 2) if amount_scaleds else None
        )
        if min_amount_wan is not None and (amount_wan is None or amount_wan < min_amount_wan):
            continue
        flows.append(
            RegionFlow(
                from_region=src,
                to_region=dst,
                edge_count=len(group),
                amount_edges=len(amount_scaleds),
                amount_wan=amount_wan,
                total_share_percent=round(sum(ratios) / 10**6, 6) if ratios else None,
                ratio_missing_edges=len(group) - len(ratios),
            )
        )

    flows.sort(key=lambda f: (-(f.amount_wan or 0.0), -f.edge_count, f.from_region, f.to_region))
    return flows[:limit] if limit is not None else flows


def region_summary(edges: list[FlowEdge]) -> dict:
    """省级流入/流出/净额/活跃度 + 集中度 HHI + 数据完备性计数。"""
    flows = aggregate_flows(edges)
    outflow: dict[str, float] = defaultdict(float)
    inflow: dict[str, float] = defaultdict(float)
    outflow_edges: dict[str, int] = defaultdict(int)
    inflow_edges: dict[str, int] = defaultdict(int)
    regions: set[str] = set()
    internal_edges = 0
    unknown_region_edges = 0

    for e in edges:
        if e.from_region == e.to_region:
            internal_edges += 1
            regions.add(e.from_region)
            continue
        regions.update((e.from_region, e.to_region))
        amount = (e.amount_scaled or 0) * AMOUNT_WAN_PER_SCALED
        outflow[e.from_region] += amount
        inflow[e.to_region] += amount
        outflow_edges[e.from_region] += 1
        inflow_edges[e.to_region] += 1

    total_outflow = sum(outflow.values())
    hhi: float | None = None
    if total_outflow > 0:
        # 份额以百分点计：HHI = Σ (份额百分点)²，范围 0..10000
        hhi = round(sum((v / total_outflow * 100) ** 2 for v in outflow.values()), 2)

    return {
        "regions": [
            {
                "region": code,
                "inflow_wan": round(inflow.get(code, 0.0), 2),
                "outflow_wan": round(outflow.get(code, 0.0), 2),
                "net_wan": round(inflow.get(code, 0.0) - outflow.get(code, 0.0), 2),
                "outflow_edges": outflow_edges.get(code, 0),
                "inflow_edges": inflow_edges.get(code, 0),
            }
            for code in sorted(regions)
        ],
        "hhi": hhi,
        "flow_count": len(flows),
        "internal_edges": internal_edges,
        "unknown_region_edges": unknown_region_edges,
        "total_cross_amount_wan": round(total_outflow, 2),
    }


def flow_timeline(edges: list[FlowEdge]) -> list[dict]:
    """按声明 valid_from 年度聚合跨区域流动趋势，升序。"""
    by_year: dict[int, list[FlowEdge]] = defaultdict(list)
    for e in cross_region(edges):
        by_year[e.year].append(e)
    return [
        {
            "year": year,
            "edge_count": len(group),
            "amount_wan": round(
                sum(e.amount_scaled or 0 for e in group) * AMOUNT_WAN_PER_SCALED, 2
            ),
            "amount_missing_edges": sum(1 for e in group if e.amount_scaled is None),
        }
        for year, group in sorted(by_year.items())
    ]


def industry_flows(pairs: list[tuple[FlowEdge, str | None]]) -> dict:
    """省（流出方）→ 行业（标的方行业）聚合，桑基图输入。

    行业缺失的边不计入聚合，以 missing_industry_edges 显式计数。
    """
    buckets: dict[tuple[str, str], list[FlowEdge]] = defaultdict(list)
    missing_industry_edges = 0
    for edge, industry in pairs:
        if edge.from_region == edge.to_region:
            continue
        if not industry:
            missing_industry_edges += 1
            continue
        buckets[(edge.from_region, industry)].append(edge)

    rows: list[dict[str, Any]] = [
        {
            "from_region": src,
            "industry": ind,
            "edge_count": len(group),
            "amount_wan": round(
                sum(e.amount_scaled or 0 for e in group) * AMOUNT_WAN_PER_SCALED, 2
            ),
        }
        for (src, ind), group in buckets.items()
    ]
    rows.sort(key=lambda r: (-r["amount_wan"], -r["edge_count"], r["from_region"]))
    return {"rows": rows, "missing_industry_edges": missing_industry_edges}
