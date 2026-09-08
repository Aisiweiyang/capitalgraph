"""穿透结果分析：聚合、环路、交叉持股、UBO 候选。

所有输出都是“候选/证据引用”，附规则说明；UBO 不构成法律认定。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from fractions import Fraction

from cg_domain.models import PenetrationConfig
from cg_domain.orm import RATIO_SCALE

from cg_capital_graph.engine import (
    ALGORITHM_VERSION,
    GraphEdge,
    PathResult,
    PenetrationResult,
    build_adjacency,
    iter_frontier,
)

_SCALE_F = Fraction(RATIO_SCALE)


def scaled_to_fraction(scaled: int) -> Fraction:
    return Fraction(scaled, RATIO_SCALE)


def fraction_to_scaled(value: Fraction) -> int:
    """banker's rounding 到 1e-8 精度，输出边界唯一舍入点。"""
    return round(value * _SCALE_F)


@dataclass(frozen=True)
class ShareholderAggregate:
    entity_id: str
    effective_scaled: int
    direct_scaled: int | None
    path_count: int
    via_missing_ratio: bool
    statement_ids: tuple[str, ...]


@dataclass(frozen=True)
class CrossHolding:
    entity_a: str
    entity_b: str
    path_a_to_b: tuple[str, ...]
    path_b_to_a: tuple[str, ...]


@dataclass(frozen=True)
class UBOCandidate:
    entity_id: str
    effective_scaled: int
    voting_scaled: int | None
    has_control_statement: bool
    basis: tuple[str, ...]  # 命中的规则编号与说明
    confidence: float
    statement_ids: tuple[str, ...]
    is_candidate: bool = True  # 恒为候选，永不输出“认定”


def aggregate_by_shareholder(result: PenetrationResult) -> list[ShareholderAggregate]:
    """按股东聚合有效权益：Σ 简单路径乘积；缺比例路径只计数并打 unknown 标。"""
    effective: dict[str, Fraction] = {}
    direct: dict[str, Fraction] = {}
    path_count: dict[str, int] = {}
    missing: dict[str, bool] = {}
    statements: dict[str, set[str]] = {}

    for path in result.paths:
        if len(path.nodes) < 2:
            continue
        shareholder = path.nodes[-1]
        path_count[shareholder] = path_count.get(shareholder, 0) + 1
        if path.missing_ratio:
            missing[shareholder] = True
        else:
            effective[shareholder] = effective.get(shareholder, Fraction(0)) + path.product
        statements.setdefault(shareholder, set()).update(path.statement_ids)
        if len(path.nodes) == 2 and not path.missing_ratio:
            direct[shareholder] = path.product

    aggregates = [
        ShareholderAggregate(
            entity_id=eid,
            effective_scaled=fraction_to_scaled(frac),
            direct_scaled=fraction_to_scaled(direct[eid]) if eid in direct else None,
            path_count=path_count[eid],
            via_missing_ratio=missing.get(eid, False),
            statement_ids=tuple(sorted(statements[eid])),
        )
        for eid, frac in sorted(effective.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    # 只出现在缺比例路径中的股东也要列出（unknown 显式化）
    for eid in sorted(set(path_count) - set(effective)):
        aggregates.append(
            ShareholderAggregate(
                entity_id=eid,
                effective_scaled=0,
                direct_scaled=None,
                path_count=path_count[eid],
                via_missing_ratio=True,
                statement_ids=tuple(sorted(statements[eid])),
            )
        )
    return aggregates


def detect_cycles(
    edges: list[GraphEdge], *, direction: str = "up", limit: int = 50
) -> list[list[str]]:
    """持股子图上的环检测（迭代 DFS，三色标记）。返回节点环列表（有界）。"""
    adj = build_adjacency(edges, direction)
    color: dict[str, int] = {}  # 0=white 1=gray 2=black
    on_stack: list[str] = []
    cycles: list[list[str]] = []

    def dfs(root: str) -> None:
        stack: list[tuple[str, int]] = [(root, 0)]
        while stack:
            node, phase = stack.pop()
            if phase == 0:
                if color.get(node, 0) != 0:
                    continue
                color[node] = 1
                on_stack.append(node)
                stack.append((node, 1))
                nxts = []
                for edge in adj.get(node, []):
                    nxts.append(edge.subject if direction == "up" else edge.obj)
                for nxt in sorted(nxts, reverse=True):
                    nxt_color = color.get(nxt, 0)
                    if nxt_color == 0:
                        stack.append((nxt, 0))
                    elif nxt_color == 1 and nxt in on_stack:
                        cycle = [*on_stack[on_stack.index(nxt) :], nxt]
                        if cycle not in cycles and len(cycles) < limit:
                            cycles.append(cycle)
            else:
                color[node] = 2
                if on_stack and on_stack[-1] == node:
                    on_stack.pop()

    for node in sorted(adj):
        if color.get(node, 0) == 0:
            dfs(root=node)
        if len(cycles) >= limit:
            break
    return cycles


def cross_holdings(
    edges: list[GraphEdge], *, max_nodes: int = 500, max_pairs: int = 200
) -> list[CrossHolding]:
    """互相可达的节点对（A→B 且 B→A，持股边），即交叉持股。

    为控制成本：仅在持股边出度 > 0 的节点集合内做有界可达性检查，
    检查节点数与输出对数均有上限（超出部分不承诺完整，见 DELIVERY 已知限制）。
    """
    adj = build_adjacency(edges, "up")
    holders = [n for n in sorted(adj) if adj[n]]
    if len(holders) > max_nodes:
        holders = holders[:max_nodes]
    results: list[CrossHolding] = []
    reach_cache: dict[str, set[str]] = {}

    def reach(node: str) -> set[str]:
        if node not in reach_cache:
            reach_cache[node] = set(iter_frontier(adj, node, max_nodes)) - {node}
        return reach_cache[node]

    for i, a in enumerate(holders):
        for b in holders[i + 1 :]:
            if b in reach(a) and a in reach(b):
                results.append(CrossHolding(entity_a=a, entity_b=b, path_a_to_b=(), path_b_to_a=()))
                if len(results) >= max_pairs:
                    return results
    return results


@dataclass(frozen=True)
class UBOBasis:
    R1 = "R1: 聚合有效权益 ≥ 阈值"
    R2 = "R2: 聚合表决权 > 50%（或存在显式控制声明）"


def ubo_candidates(
    result: PenetrationResult,
    edges: list[GraphEdge],
    *,
    min_effective_percent: float = 25.0,
) -> list[UBOCandidate]:
    """最终受益所有人候选。

    规则（输出附依据，永不输出“认定”）：
    - R1: 聚合有效持股 ≥ min_effective_percent（默认 25%）；
    - R2: 聚合表决权 > 50%，或存在指向目标的显式 controls 声明路径；
    - 自然人与法人都会进入候选，kind 信息由调用方提供用于前端着色。
    置信度 = 路径上最小声明置信度；缺比例路径只提示 unknown，不参与数值判定。
    """
    threshold = Fraction(round(min_effective_percent * 10**6), 10**8)

    edge_by_id = {e.statement_id: e for e in edges}

    effective: dict[str, Fraction] = {}
    statements: dict[str, set[str]] = {}
    for path in result.paths:
        if len(path.nodes) < 2 or path.missing_ratio:
            continue
        holder = path.nodes[-1]
        effective[holder] = effective.get(holder, Fraction(0)) + path.product
        statements.setdefault(holder, set()).update(path.statement_ids)
    for path in result.control_paths:
        if len(path.nodes) >= 2:
            holder = path.nodes[-1]
            statements.setdefault(holder, set()).update(path.statement_ids)

    # 表决权按与持股相同的路径乘积法聚合（voting 缺失时跳过该段）
    voting = _aggregate_voting(result, edge_by_id)

    has_control: set[str] = set()
    for path in result.control_paths:
        if len(path.nodes) >= 2:
            has_control.add(path.nodes[-1])

    candidates: list[UBOCandidate] = []
    for holder in sorted(set(effective) | set(voting) | has_control):
        eff = effective.get(holder, Fraction(0))
        basis: list[str] = []
        if eff >= threshold:
            basis.append(UBOBasis.R1)
        vote_scaled = fraction_to_scaled(voting[holder]) if holder in voting else None
        if (vote_scaled is not None and vote_scaled * 2 > RATIO_SCALE) or holder in has_control:
            basis.append(UBOBasis.R2)
        if not basis:
            continue
        sids = sorted(statements.get(holder, set()))
        confidence = 1.0
        for sid in sids:
            edge = edge_by_id.get(sid)
            if edge is not None:
                confidence = min(confidence, edge.confidence)
        candidates.append(
            UBOCandidate(
                entity_id=holder,
                effective_scaled=fraction_to_scaled(eff),
                voting_scaled=vote_scaled,
                has_control_statement=holder in has_control,
                basis=tuple(basis),
                confidence=round(confidence, 6),
                statement_ids=tuple(sids),
            )
        )
    candidates.sort(key=lambda c: (-c.effective_scaled, c.entity_id))
    return candidates


def _aggregate_voting(
    result: PenetrationResult, edge_by_id: dict[str, GraphEdge]
) -> dict[str, Fraction]:
    """表决权路径乘积聚合；某段表决权缺失时按 1 处理并整条路径计 unknown（此处跳过）。"""
    voting: dict[str, Fraction] = {}
    for path in result.paths:
        if len(path.nodes) < 2 or path.missing_ratio:
            continue
        product = Fraction(1)
        complete = True
        for sid in path.statement_ids:
            edge = edge_by_id.get(sid)
            if edge is None or edge.voting_scaled is None:
                complete = False
                break
            product *= Fraction(edge.voting_scaled, RATIO_SCALE)
        if complete:
            holder = path.nodes[-1]
            voting[holder] = voting.get(holder, Fraction(0)) + product
    return voting


@dataclass(frozen=True)
class AnalysisReport:
    aggregates: list[ShareholderAggregate]
    cycles: list[list[str]]
    cross: list[CrossHolding]
    ubo: list[UBOCandidate]
    algorithm_version: str = ALGORITHM_VERSION
    config_hash: str = ""
    warnings: list[str] = field(default_factory=list)


def config_hash(config: PenetrationConfig) -> str:
    return hashlib.sha256(config.canonical_json().encode("utf-8")).hexdigest()


def analyse(
    root: str,
    result: PenetrationResult,
    edges: list[GraphEdge],
    config: PenetrationConfig,
    *,
    entity_kind: dict[str, str] | None = None,
) -> AnalysisReport:
    warnings: list[str] = []
    if result.truncated:
        warnings.append("已达路径/节点上限，结果可能不完整（truncated=true）")
    aggregates = aggregate_by_shareholder(result)
    report = AnalysisReport(
        aggregates=aggregates,
        cycles=result.cycles or detect_cycles(edges),
        cross=cross_holdings(edges),
        ubo=ubo_candidates(
            result,
            edges,
            min_effective_percent=25.0,
        ),
        algorithm_version=ALGORITHM_VERSION,
        config_hash=config_hash(config),
        warnings=warnings,
    )
    return report


def result_to_jsonable(
    report: AnalysisReport,
    result: PenetrationResult,
    *,
    entity_kind: dict[str, str] | None = None,
) -> dict:
    """序列化为 API 输出：比例统一输出为百分数（6 位小数），unknown 显式。"""
    kinds = entity_kind or {}

    def pct(scaled: int | None) -> float | None:
        return None if scaled is None else round(scaled * 100.0 / RATIO_SCALE, 6)

    def path_json(path: PathResult) -> dict:
        return {
            "nodes": list(path.nodes),
            "statement_ids": list(path.statement_ids),
            "product_percent": pct(fraction_to_scaled(path.product)),
            "missing_ratio": path.missing_ratio,
        }

    return {
        "root": result.root,
        "direction": result.direction,
        "truncated": result.truncated,
        "visited_nodes": result.visited_nodes,
        "paths": [path_json(p) for p in result.paths],
        "control_paths": [path_json(p) for p in result.control_paths],
        "cycles": [list(c) for c in report.cycles],
        "cross_holdings": [{"entity_a": c.entity_a, "entity_b": c.entity_b} for c in report.cross],
        "aggregates": [
            {
                "entity_id": a.entity_id,
                "entity_kind": kinds.get(a.entity_id),
                "effective_percent": pct(a.effective_scaled),
                "direct_percent": pct(a.direct_scaled),
                "path_count": a.path_count,
                "unknown_ratio": a.via_missing_ratio,
                "statement_ids": list(a.statement_ids),
            }
            for a in report.aggregates
        ],
        "ubo_candidates": [
            {
                "entity_id": c.entity_id,
                "entity_kind": kinds.get(c.entity_id),
                "effective_percent": pct(c.effective_scaled),
                "voting_percent": pct(c.voting_scaled),
                "has_control_statement": c.has_control_statement,
                "basis": list(c.basis),
                "confidence": c.confidence,
                "statement_ids": list(c.statement_ids),
            }
            for c in report.ubo
        ],
        "assumptions": result.assumptions,
        "warnings": report.warnings,
        "algorithm_version": report.algorithm_version,
        "config_hash": report.config_hash,
    }
