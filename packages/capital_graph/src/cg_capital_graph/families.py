"""系族识别（资本系谱）：从时点有效的控制类边聚类"谁在控制一片企业"。

口径（ADR-016，与穿透引擎同源：控制语义不由比例推导，缺失显式化）：
- 控制类边 = controls 声明 + 比例 ≥ 阈值（默认 50%）的 holds_shares 声明；
  缺比例的 holds_shares 不构成控制边，以 missing_ratio_holding_edges 显式计数；
- 控制人根：非企业实体（默认 person/government_body，可配置）。kind 缺失或企业
  实体一律不作根（宁缺毋错，不编造控制人）；
- 聚类：从每个控制人沿控制方向 BFS 收集可达实体并记录被控路径；同一实体被多个
  控制人可达 → 并族（共同实控人）。交叉持股环上的实体被环外控制人与环内控制人
  同时可达，因此随共同可达自然并族（union-find 实现，不引入图数据库）；
- 无控制人可达的连通分量不成族，其实体计入 unassigned_entity_count；
- 族 ID = 族内控制人集合中排序最小的实体 ID；全部输出排序确定，同输入同输出。

护栏：单控制人遍历的成员数与路径深度有界，命中即停止并打 truncated 标记；
族内环路数有界。返回值仅由 (edges, entity_kind, config, region_by_entity) 决定。
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from cg_capital_graph.analysis import detect_cycles
from cg_capital_graph.engine import GraphEdge
from cg_capital_graph.flows import AMOUNT_WAN_PER_SCALED, FlowEdge

FAMILIES_ALGORITHM_VERSION = "cg-families/1.0.0"

FAMILIES_ASSUMPTIONS: tuple[str, ...] = (
    "控制类边 = controls 声明 + 比例 ≥ 阈值的 holds_shares 声明；缺比例的持股边不构成控制边；",
    "控制人根仅限非企业实体（自然人/政府国资等）；无控制人可达的实体不成族并显式计数；",
    "并族条件 = 共同实控人（交叉持股环上的实体因被环内外控制人共同可达而自然并族）；",
    "结果为算法候选，仅供研究参考，不构成法律认定或投资建议。",
)

_DEFAULT_NON_BUSINESS = ("person", "government_body")


@dataclass(frozen=True)
class FamiliesConfig:
    """系族算法配置。全字段参与配置哈希，保证结果可追溯到口径。"""

    min_control_ratio_percent: float = 50.0
    non_business_kinds: tuple[str, ...] = _DEFAULT_NON_BUSINESS
    max_members_per_family: int = 1000  # 单控制人一次遍历可收集的成员上限（含控制人）
    max_path_depth: int = 8  # 被控路径摘要的最大边数
    max_internal_cycles: int = 50  # 单族环路输出上限

    def canonical_json(self) -> str:
        return json.dumps(
            {
                "max_internal_cycles": self.max_internal_cycles,
                "max_members_per_family": self.max_members_per_family,
                "max_path_depth": self.max_path_depth,
                "min_control_ratio_percent": self.min_control_ratio_percent,
                "non_business_kinds": list(self.non_business_kinds),
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemberInfo:
    """族成员及其被控路径摘要（控制人 → … → 成员）。"""

    entity_id: str
    controller: str  # 首个到达该成员的控制人
    path: tuple[str, ...]
    statement_ids: tuple[str, ...]
    depth: int  # 路径边数


@dataclass(frozen=True)
class Family:
    """一个系族：控制人组 + 成员、路径、密度、区域分布与族内环路。"""

    family_id: str
    controllers: tuple[str, ...]
    members: tuple[MemberInfo, ...]
    internal_edge_count: int
    density: float | None  # 族内控制类边数 / (n*(n-1))；n<2 无定义 → None
    region_distribution: tuple[tuple[str, int], ...]  # (region_code, 成员数)，按代码排序
    region_unknown: int
    cycle_count: int
    truncated: bool = False
    algorithm_version: str = FAMILIES_ALGORITHM_VERSION

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def region_coverage(self) -> int:
        """覆盖的省份数（region 缺失的成员不计入，见 region_unknown）。"""
        return len(self.region_distribution)


@dataclass(frozen=True)
class FamiliesResult:
    """系族识别总输出。families 按 (成员数降序, 族ID) 排序。"""

    families: tuple[Family, ...]
    unassigned_entity_count: int  # 出现在控制类边中但不属于任何族的实体数
    missing_ratio_holding_edges: int  # 因缺比例被排除的持股边数
    config_hash: str
    algorithm_version: str = FAMILIES_ALGORITHM_VERSION
    assumptions: tuple[str, ...] = FAMILIES_ASSUMPTIONS
    unassigned_entities: tuple[str, ...] = ()


def _threshold_scaled(percent: float) -> int:
    return int(Fraction(round(percent * 10**6)))


def _control_edges(edges: list[GraphEdge], config: FamiliesConfig) -> tuple[list[GraphEdge], int]:
    """过滤控制类边；返回 (控制类边, 缺比例被排除的持股边数)。"""
    threshold = _threshold_scaled(config.min_control_ratio_percent)
    control: list[GraphEdge] = []
    missing = 0
    for e in edges:
        if e.predicate == "controls":
            control.append(e)
        elif e.predicate == "holds_shares":
            if e.share_scaled is None:
                missing += 1
            elif e.share_scaled >= threshold:
                control.append(e)
    return control, missing


class _UnionFind:
    """控制人并查集：较小根为父，合并结果与合并顺序无关（确定性）。"""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # 路径压缩
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            lo, hi = sorted((ra, rb))
            self.parent[hi] = lo


def identify_families(
    edges: list[GraphEdge],
    entity_kind: dict[str, str],
    config: FamiliesConfig | None = None,
    *,
    region_by_entity: dict[str, str | None] | None = None,
) -> FamiliesResult:
    """系族识别。输入为时点有效的声明边与实体类型映射，输出确定且可复现。"""
    cfg = config or FamiliesConfig()
    regions = region_by_entity or {}
    control, missing = _control_edges(edges, cfg)

    # 邻接表（控制方向 subject→obj），按键排序保证遍历顺序确定
    adj: dict[str, list[GraphEdge]] = defaultdict(list)
    for e in control:
        adj[e.subject].append(e)
    for key in adj:
        adj[key].sort(key=lambda e: (e.obj, e.statement_id))

    non_business = set(cfg.non_business_kinds)
    seeds = sorted({e.subject for e in control if entity_kind.get(e.subject) in non_business})

    uf = _UnionFind()
    visited: dict[str, MemberInfo] = {}  # 成员 → 首次到达信息（来自排序更小的控制人）
    truncated_by_seed: dict[str, bool] = {}

    for seed in seeds:
        uf.find(seed)
        members: dict[str, MemberInfo] = {seed: MemberInfo(seed, seed, (seed,), (), 0)}
        truncated = False
        queue: deque[tuple[str, int]] = deque([(seed, 0)])
        while queue and not truncated:
            node, depth = queue.popleft()
            for edge in adj.get(node, ()):
                nxt = edge.obj
                if nxt in members:
                    continue
                if len(members) >= cfg.max_members_per_family or depth + 1 > cfg.max_path_depth:
                    truncated = True
                    break
                members[nxt] = MemberInfo(
                    entity_id=nxt,
                    controller=seed,
                    path=(*members[node].path, nxt),
                    statement_ids=(*members[node].statement_ids, edge.statement_id),
                    depth=depth + 1,
                )
                queue.append((nxt, depth + 1))
        truncated_by_seed[seed] = truncated

        for eid, info in members.items():
            prev = visited.get(eid)
            if prev is None:
                visited[eid] = info
            else:
                uf.union(seed, prev.controller)  # 共同可达 → 并族

    # 按并查集根聚合：成员随其首次到达控制人归族
    grouped_members: dict[str, dict[str, MemberInfo]] = defaultdict(dict)
    grouped_seeds: dict[str, list[str]] = defaultdict(list)
    for seed in seeds:
        grouped_seeds[uf.find(seed)].append(seed)
    for eid, info in visited.items():
        grouped_members[uf.find(info.controller)][eid] = info

    member_entity_ids = set(visited)
    families: list[Family] = []
    for root in sorted(grouped_members):
        members_map = grouped_members[root]
        seeds_in_family = sorted(grouped_seeds.get(root, ()))
        fam_ids = set(members_map)
        internal = [e for e in control if e.subject in fam_ids and e.obj in fam_ids]
        n = len(members_map)
        density = round(len(internal) / (n * (n - 1)), 6) if n >= 2 else None

        region_counts: dict[str, int] = defaultdict(int)
        region_unknown = 0
        for eid in members_map:
            code = regions.get(eid)
            if code:
                region_counts[code] += 1
            else:
                region_unknown += 1

        families.append(
            Family(
                family_id=root,
                controllers=tuple(seeds_in_family),
                members=tuple(sorted(members_map.values(), key=lambda m: m.entity_id)),
                internal_edge_count=len(internal),
                density=density,
                region_distribution=tuple(sorted(region_counts.items())),
                region_unknown=region_unknown,
                cycle_count=len(
                    detect_cycles(internal, direction="down", limit=cfg.max_internal_cycles)
                ),
                truncated=any(truncated_by_seed.get(s, False) for s in seeds_in_family),
            )
        )

    families.sort(key=lambda f: (-f.member_count, f.family_id))

    all_entities = {e.subject for e in control} | {e.obj for e in control}
    unassigned = tuple(sorted(all_entities - member_entity_ids))
    return FamiliesResult(
        families=tuple(families),
        unassigned_entity_count=len(unassigned),
        missing_ratio_holding_edges=missing,
        config_hash=cfg.canonical_hash(),
        unassigned_entities=unassigned,
    )


def family_flows(edges: list[FlowEdge], family_by_entity: dict[str, str]) -> dict:
    """族间资本流向：把流动边按（族，族）分组聚合。

    同族边计入 intra_family_edges；任一端无族的边计入 ungrouped_edges，不进聚合；
    缺失金额的边计入 amount_missing_edges，金额合计绝不含估算值。
    """
    buckets: dict[tuple[str, str], list[FlowEdge]] = defaultdict(list)
    intra = 0
    ungrouped = 0
    for e in edges:
        src = family_by_entity.get(e.subject_id or "", "")
        dst = family_by_entity.get(e.object_id or "", "")
        if not src or not dst:
            ungrouped += 1
            continue
        if src == dst:
            intra += 1
            continue
        buckets[(src, dst)].append(e)

    rows: list[dict[str, Any]] = [
        {
            "from_family": src,
            "to_family": dst,
            "edge_count": len(group),
            "amount_edges": sum(1 for e in group if e.amount_scaled is not None),
            "amount_wan": (
                round(
                    sum(e.amount_scaled for e in group if e.amount_scaled is not None)
                    * AMOUNT_WAN_PER_SCALED,
                    2,
                )
                if any(e.amount_scaled is not None for e in group)
                else None
            ),
            "amount_missing_edges": sum(1 for e in group if e.amount_scaled is None),
        }
        for (src, dst), group in buckets.items()
    ]
    rows.sort(
        key=lambda r: (
            -(r["amount_wan"] or 0.0),
            -r["edge_count"],
            r["from_family"],
            r["to_family"],
        )
    )
    return {
        "rows": rows,
        "intra_family_edges": intra,
        "ungrouped_edges": ungrouped,
        "algorithm_version": FAMILIES_ALGORITHM_VERSION,
    }
