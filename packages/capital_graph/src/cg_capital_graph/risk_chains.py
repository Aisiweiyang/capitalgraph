"""担保与质押风险传导（纯函数、确定性、无 IO）。

口径（ADR-016）：
- 担保边 provides_guarantee：subject=担保人（被担保方出险时代偿），object=被担保人；
  名义金额用结构化 amount_scaled；缺失金额的边显式计数，绝不补值；
- 链条沿"义务方向"（被担保人 → 担保人）回溯：从起点出发的每条简单路径输出为链；
- 环 = 声明方向（担保人 → 被担保人）上的环路，即互保圈；输出规范化为
  （最小节点起头、含回到起点的收尾节点）并去重；
- 传导：出险集合沿义务方向逐层扩散（BFS，受累实体去重），每层名义金额为引发该层
  的担保边金额合计；任一边缺金额 → 该层 nominal=None；总计仅当全部金额齐备时输出；
- 质押 pledges_shares 不参与链式传导（风险敞口在实体层面展示，见 API 层）。

返回值仅由 (edges, 起点/出险集合, config) 决定；输入摘要为排序后的确定性 sha256。
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass

RISK_CHAINS_ALGORITHM_VERSION = "cg-risk-chains/1.0.0"


@dataclass(frozen=True)
class GuaranteeEdge:
    """一条担保声明。amount_scaled 为担保金额（万元×100），None=来源未给出。"""

    statement_id: str
    guarantor: str  # 担保人（subject）
    beneficiary: str  # 被担保人（object）
    amount_scaled: int | None


@dataclass(frozen=True)
class RiskChainsConfig:
    """风险链算法配置。全字段参与配置哈希。"""

    max_depth: int = 6  # 链条/传导的最大跳数
    max_chains: int = 100  # 单起点链条输出上限
    max_cycles: int = 50  # 环路输出上限

    def canonical_json(self) -> str:
        return json.dumps(
            {
                "max_chains": self.max_chains,
                "max_cycles": self.max_cycles,
                "max_depth": self.max_depth,
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GuaranteeChain:
    """从起点沿义务方向的一条担保链：path[0]=起点（被担保方），末位=最终担保人。"""

    path: tuple[str, ...]
    statement_ids: tuple[str, ...]
    nominal_amount_scaled: int | None  # 链上金额合计；任一段缺失 → None
    amount_missing_edges: int


@dataclass(frozen=True)
class PropagationLevel:
    """传导的一层：本轮新受累实体与引发它的担保边金额。"""

    depth: int
    newly_affected: tuple[str, ...]
    nominal_amount_scaled: int | None
    amount_missing_edges: int


@dataclass(frozen=True)
class RiskPropagation:
    """一次传导模拟结果。出险集合沿义务方向逐层扩散。"""

    origin: tuple[str, ...]  # 初始出险集合（排序）
    levels: tuple[PropagationLevel, ...]
    affected_entities: tuple[str, ...]  # 全部受累实体（不含初始出险，排序）
    total_nominal_scaled: int | None  # 全部金额齐备时的合计，否则 None
    total_amount_missing_edges: int
    algorithm_version: str = RISK_CHAINS_ALGORITHM_VERSION


def _obligation_adj(edges: list[GuaranteeEdge]) -> dict[str, list[GuaranteeEdge]]:
    """义务方向邻接：beneficiary → 为其担保的边（出险沿此方向传导）。"""
    adj: dict[str, list[GuaranteeEdge]] = defaultdict(list)
    for e in edges:
        adj[e.beneficiary].append(e)
    for key in adj:
        adj[key].sort(key=lambda e: (e.guarantor, e.statement_id))
    return dict(adj)


def guarantee_chains(
    edges: list[GuaranteeEdge], start: str, config: RiskChainsConfig | None = None
) -> list[GuaranteeChain]:
    """从 start 出发沿义务方向的所有简单担保链（BFS 有界，输出按路径排序）。"""
    cfg = config or RiskChainsConfig()
    adj = _obligation_adj(edges)
    chains: list[GuaranteeChain] = []
    # 队列元素：(路径, 声明ID, 金额合计, 缺失边数, 金额是否齐备)
    queue: deque[tuple[tuple[str, ...], tuple[str, ...], int, int, bool]] = deque()
    queue.append(((start,), (), 0, 0, True))
    while queue and len(chains) < cfg.max_chains:
        path, sids, amount, missing, complete = queue.popleft()
        node = path[-1]
        depth = len(path) - 1
        for edge in adj.get(node, ()):
            if edge.guarantor in path:
                continue  # 简单路径：环由 guarantee_cycles 单独呈现
            new_amount = amount + (edge.amount_scaled or 0)
            new_missing = missing + (0 if edge.amount_scaled is not None else 1)
            chains.append(
                GuaranteeChain(
                    path=(*path, edge.guarantor),
                    statement_ids=(*sids, edge.statement_id),
                    nominal_amount_scaled=(new_amount if new_missing == 0 else None),
                    amount_missing_edges=new_missing,
                )
            )
            if len(chains) >= cfg.max_chains:
                break
            if depth + 1 < cfg.max_depth:
                queue.append(
                    (
                        (*path, edge.guarantor),
                        (*sids, edge.statement_id),
                        new_amount,
                        new_missing,
                        complete and edge.amount_scaled is not None,
                    )
                )
    chains.sort(key=lambda c: (c.path, c.statement_ids))
    return chains


def guarantee_cycles(
    edges: list[GuaranteeEdge], config: RiskChainsConfig | None = None
) -> list[tuple[str, ...]]:
    """互保圈检测：声明方向（担保人→被担保人）上的环，规范化输出。"""
    cfg = config or RiskChainsConfig()
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e.guarantor].append(e.beneficiary)
    for key in adj:
        adj[key] = sorted(set(adj[key]))

    color: dict[str, int] = {}
    on_stack: list[str] = []
    raw: list[list[str]] = []

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
                for nxt in sorted(adj.get(node, ()), reverse=True):
                    c = color.get(nxt, 0)
                    if c == 0:
                        stack.append((nxt, 0))
                    elif c == 1 and nxt in on_stack:
                        cycle = [*on_stack[on_stack.index(nxt) :], nxt]
                        if cycle not in raw and len(raw) < cfg.max_cycles:
                            raw.append(cycle)
            else:
                color[node] = 2
                if on_stack and on_stack[-1] == node:
                    on_stack.pop()

    for node in sorted(adj):
        if color.get(node, 0) == 0:
            dfs(node)
        if len(raw) >= cfg.max_cycles:
            break
    return canonicalize_cycles(raw)


def canonicalize_cycles(cycles: list[list[str]]) -> list[tuple[str, ...]]:
    """环规范化：旋转到最小节点起头（含收尾重复节点），去重后排序。"""
    out: set[tuple[str, ...]] = set()
    for cycle in cycles:
        if len(cycle) < 2:
            continue
        nodes = cycle[:-1] if cycle[0] == cycle[-1] else list(cycle)
        if not nodes:
            continue
        min_i = nodes.index(min(nodes))
        rotated = [*nodes[min_i:], *nodes[:min_i]]
        out.add((*rotated, rotated[0]))
    return sorted(out)


def propagate_risk(
    edges: list[GuaranteeEdge],
    distressed: set[str],
    config: RiskChainsConfig | None = None,
) -> RiskPropagation:
    """传导模拟：出险集合沿义务方向逐层扩散，受累实体去重，金额缺失显式。

    注意：distressed 集合在本函数内演进（出险 ∪ 已受累），输入集合不被修改。
    """
    cfg = config or RiskChainsConfig()
    adj = _obligation_adj(edges)
    origins = tuple(sorted(distressed))
    in_distress = set(distressed)  # 出险 + 已受累
    affected: set[str] = set()  # 仅新受累（不含初始出险）
    levels: list[PropagationLevel] = []
    total_amount = 0
    total_missing = 0

    frontier = set(distressed)
    for depth in range(1, cfg.max_depth + 1):
        triggered: dict[str, list[GuaranteeEdge]] = defaultdict(list)
        for node in frontier:
            for edge in adj.get(node, ()):
                if edge.guarantor in in_distress:
                    continue
                triggered[edge.guarantor].append(edge)
        if not triggered:
            break
        newly = tuple(sorted(triggered))
        level_amount = 0
        level_missing = 0
        for used in triggered.values():
            for edge in used:
                if edge.amount_scaled is None:
                    level_missing += 1
                else:
                    level_amount += edge.amount_scaled
        levels.append(
            PropagationLevel(
                depth=depth,
                newly_affected=newly,
                nominal_amount_scaled=(level_amount if level_missing == 0 else None),
                amount_missing_edges=level_missing,
            )
        )
        total_amount += level_amount
        total_missing += level_missing
        affected.update(newly)
        in_distress.update(newly)
        frontier = set(newly)

    complete = total_missing == 0
    return RiskPropagation(
        origin=origins,
        levels=tuple(levels),
        affected_entities=tuple(sorted(affected)),
        total_nominal_scaled=(total_amount if complete and affected else None),
        total_amount_missing_edges=total_missing,
    )


def input_digest(edges: list[GuaranteeEdge]) -> str:
    """输入版本：边集按内容排序后的 sha256（与顺序无关，可复现）。"""
    canonical = json.dumps(
        sorted((e.statement_id, e.guarantor, e.beneficiary, e.amount_scaled) for e in edges),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
