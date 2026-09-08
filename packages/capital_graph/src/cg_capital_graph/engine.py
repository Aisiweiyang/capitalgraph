"""穿透遍历引擎。

方向约定：
- up（向上穿透）：从目标企业出发找股东。遍历边 obj == 当前节点。
- down（对外投资）：从股东出发找被投企业。遍历边 subject == 当前节点。

确定性保障：
- 邻接表按键排序后遍历；
- 路径只走简单路径（不重复节点），环路显式记录；
- 全部护栏（深度/路径数/节点数）命中即停止并打 truncated 标记；
- 超时不返回部分结果而是抛错——保证任何返回结果都与输入和配置一一对应。
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from fractions import Fraction

from cg_domain.models import PenetrationConfig

ALGORITHM_VERSION = "cg-penetration/1.0.0"

_UNIT = Fraction(1)


@dataclass(frozen=True)
class GraphEdge:
    """一条持股/控制边。share 为 0..1e8 缩放整数，None 表示来源缺失。"""

    statement_id: str
    subject: str
    obj: str
    predicate: str
    share_scaled: int | None
    voting_scaled: int | None
    confidence: float = 1.0

    def ratio_fraction(self) -> Fraction | None:
        if self.share_scaled is None:
            return None
        return Fraction(self.share_scaled, 10**8)


@dataclass
class PathResult:
    nodes: list[str]
    statement_ids: list[str]
    product: Fraction
    missing_ratio: bool = False


@dataclass
class PenetrationResult:
    root: str
    direction: str
    paths: list[PathResult] = field(default_factory=list)
    control_paths: list[PathResult] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    truncated: bool = False
    visited_nodes: int = 0

    @property
    def assumptions(self) -> list[str]:
        notes = [
            "路径乘积法：有效权益 = Σ(简单路径上各段持股比例之积)；",
            "环路结构下仅枚举简单路径，聚合值可能低估循环持股网络中的真实权益；",
            "缺失比例的边不计入数值结果（unknown 显式返回，不编造数值）。",
        ]
        if self.cycles:
            notes.append(f"检测到 {len(self.cycles)} 个环路，已标记相关路径。")
        return notes


class PenetrationTimeout(Exception):
    """遍历超时。不返回部分结果，避免把时间相关的输出当作数据。"""


class PenetrationTruncated(Exception):
    """护栏命中后仍需继续才能完整——作为内部信号用于停止扩展。"""


def build_adjacency(edges: list[GraphEdge], direction: str) -> dict[str, list[GraphEdge]]:
    """按遍历方向建邻接表；排序保证同输入下遍历顺序稳定。"""
    adj: dict[str, list[GraphEdge]] = defaultdict(list)
    for edge in edges:
        if edge.predicate == "controls":
            continue  # 控制边单独在 control_paths 中呈现，不参与比例乘积
        key = edge.obj if direction == "up" else edge.subject
        adj[key].append(edge)
    for key in adj:
        adj[key].sort(key=lambda e: (e.subject, e.obj, e.statement_id))
    return dict(adj)


def _control_adjacency(edges: list[GraphEdge], direction: str) -> dict[str, list[GraphEdge]]:
    adj: dict[str, list[GraphEdge]] = defaultdict(list)
    for edge in edges:
        if edge.predicate != "controls":
            continue
        key = edge.obj if direction == "up" else edge.subject
        adj[key].append(edge)
    for key in adj:
        adj[key].sort(key=lambda e: (e.subject, e.obj, e.statement_id))
    return dict(adj)


def penetrate(
    root: str,
    edges: list[GraphEdge],
    config: PenetrationConfig,
    *,
    monotonic: Callable[[], float] = time.monotonic,
) -> PenetrationResult:
    """执行穿透。返回值仅由 (root, edges, config) 决定；超时抛 PenetrationTimeout。"""
    direction = config.direction
    adj = build_adjacency(edges, direction)
    control_adj = _control_adjacency(edges, direction)
    min_ratio_fraction = Fraction(round(config.min_ratio_percent * 10**6), 10**8)

    result = PenetrationResult(root=root, direction=direction)
    deadline = monotonic() + config.timeout_seconds
    counter = {"steps": 0}
    visited_global: set[str] = set()

    def check_budgets() -> None:
        counter["steps"] += 1
        # 超时逐步检查（开销远小于一次邻接表访问）
        if monotonic() > deadline:
            raise PenetrationTimeout(f"穿透超时（>{config.timeout_seconds}s）")
        if len(result.paths) >= config.max_paths or len(visited_global) >= config.max_nodes:
            result.truncated = True
            raise PenetrationTruncated()

    def dfs(
        node: str,
        chain_nodes: list[str],
        chain_statements: list[str],
        product: Fraction,
        missing: bool,
    ) -> None:
        visited_global.add(node)
        check_budgets()
        for edge in adj.get(node, []):
            nxt = edge.subject if direction == "up" else edge.obj
            if nxt in chain_nodes:
                # 环：记录一次（按环路节点序列去重），不递归
                cycle = chain_nodes[chain_nodes.index(nxt):] + [nxt]
                if cycle not in result.cycles and len(result.cycles) < 100:
                    result.cycles.append(cycle)
                continue
            ratio = edge.ratio_fraction()
            new_missing = missing or ratio is None
            new_product = product * (ratio if ratio is not None else _UNIT)
            if ratio is not None and new_product < min_ratio_fraction and direction == "up":
                # 有效权益低于阈值：更深的路径只会更小（比例 ≤ 1），剪枝
                continue
            new_chain = chain_nodes + [nxt]
            new_statements = chain_statements + [edge.statement_id]
            result.paths.append(
                PathResult(
                    nodes=new_chain,
                    statement_ids=new_statements,
                    product=new_product,
                    missing_ratio=new_missing,
                )
            )
            if len(new_chain) < config.max_depth:
                dfs(nxt, new_chain, new_statements, new_product, new_missing)

    try:
        dfs(root, [root], [], _UNIT, False)
    except PenetrationTruncated:
        pass

    # 直接控制声明路径（一跳即可，控制语义不由比例推导）
    for edge in control_adj.get(root, []):
        target = edge.subject if direction == "up" else edge.obj
        result.control_paths.append(
            PathResult(nodes=[root, target], statement_ids=[edge.statement_id], product=_UNIT)
        )

    result.visited_nodes = len(visited_global)
    result.paths.sort(key=lambda p: (tuple(p.nodes), tuple(p.statement_ids)))
    return result


def iter_frontier(
    adj: dict[str, list[GraphEdge]], start: str, max_nodes: int, *, direction: str = "up"
) -> Iterator[str]:
    """从 start 出发可达节点（BFS，含 start），受限 max_nodes。"""
    seen = {start}
    queue = [start]
    while queue:
        node = queue.pop(0)
        yield node
        for edge in adj.get(node, []):
            nxt = edge.subject if direction == "up" else edge.obj
            if nxt not in seen:
                seen.add(nxt)
                if len(seen) >= max_nodes:
                    return
                queue.append(nxt)
