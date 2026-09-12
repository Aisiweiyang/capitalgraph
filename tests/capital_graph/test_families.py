"""系族识别纯函数单测：聚类正确性、并族、阈值边界、缺失显式处理、确定性。

口径（ADR-016）：
- 控制类边 = controls + 比例 ≥ 阈值（默认 50%）的 holds_shares；缺比例的持股边不构成控制边；
- 控制人根仅限非企业实体（person/government_body）；kind 缺失保守地不作根；
- 并族 = 同一实体被多个控制人可达（共同实控人；交叉持股环因此自然并族）；
- 无控制人可达的连通分量不成族，显式计数。
"""

from __future__ import annotations

from cg_capital_graph import FamiliesConfig, Family, GraphEdge, identify_families
from cg_capital_graph.families import FAMILIES_ALGORITHM_VERSION, family_flows
from cg_capital_graph.flows import FlowEdge


def _edge(
    sid: str,
    subject: str,
    obj: str,
    *,
    predicate: str = "controls",
    share: int | None = None,
) -> GraphEdge:
    return GraphEdge(
        statement_id=sid,
        subject=subject,
        obj=obj,
        predicate=predicate,
        share_scaled=share,
        voting_scaled=None,
    )


_KINDS = {
    "P1": "person",
    "P2": "person",
    "P3": "government_body",
    "C1": "company",
    "C2": "company",
    "C3": "company",
    "C4": "company",
}


def _members(result, family_id: str) -> set[str]:
    fam = next(f for f in result.families if f.family_id == family_id)
    return {m.entity_id for m in fam.members}


def test_simple_two_level_family_with_paths() -> None:
    """P1 控制 C1，C1 过半持股 C2 → 一族，路径 P1→C1→C2。"""
    edges = [
        _edge("s1", "P1", "C1"),
        _edge("s2", "C1", "C2", predicate="holds_shares", share=60 * 10**6),
    ]
    result = identify_families(edges, _KINDS)
    assert len(result.families) == 1
    fam = result.families[0]
    assert fam.family_id == "P1"
    assert fam.controllers == ("P1",)
    assert {m.entity_id for m in fam.members} == {"P1", "C1", "C2"}
    c2 = next(m for m in fam.members if m.entity_id == "C2")
    assert c2.path == ("P1", "C1", "C2")
    assert c2.statement_ids == ("s1", "s2")
    assert result.unassigned_entity_count == 0


def test_threshold_boundary_inclusive_at_50_percent() -> None:
    """阈值边界：恰好 50% 构成控制边；49.999999% 不构成。"""
    edges_at = [
        _edge("s1", "P1", "C1"),
        _edge("s2", "C1", "C2", predicate="holds_shares", share=50 * 10**6),
    ]
    result = identify_families(edges_at, _KINDS)
    assert _members(result, "P1") >= {"P1", "C1", "C2"}

    edges_below = [
        _edge("s1", "P1", "C1"),
        _edge("s2", "C1", "C2", predicate="holds_shares", share=50 * 10**6 - 1),
    ]
    result_below = identify_families(edges_below, _KINDS)
    assert _members(result_below, "P1") == {"P1", "C1"}
    assert {m.entity_id for f in result_below.families for m in f.members} == {"P1", "C1"}


def test_custom_threshold_parameter() -> None:
    """阈值可配置：34% 边在默认阈值下不构成控制，在 30% 阈值下构成。"""
    edges = [
        _edge("s1", "P1", "C1"),
        _edge("s2", "C1", "C2", predicate="holds_shares", share=34 * 10**6),
    ]
    default_cfg = identify_families(edges, _KINDS, FamiliesConfig())
    assert "C2" not in _members(default_cfg, "P1")
    low_cfg = identify_families(edges, _KINDS, FamiliesConfig(min_control_ratio_percent=30.0))
    assert "C2" in _members(low_cfg, "P1")


def test_missing_ratio_holding_edge_is_not_control_and_counted() -> None:
    """缺比例的 holds_shares 不构成控制边，显式计数，绝不推断。"""
    edges = [
        _edge("s1", "P1", "C1"),
        _edge("s2", "C1", "C2", predicate="holds_shares", share=None),
    ]
    result = identify_families(edges, _KINDS)
    assert "C2" not in _members(result, "P1")
    assert result.missing_ratio_holding_edges == 1


def test_common_controlled_entity_merges_families() -> None:
    """共同实控并族：P1、P2 都控制 C1 → 一族，双控制人，族 ID 取排序最小。"""
    edges = [
        _edge("s1", "P2", "C1"),
        _edge("s2", "P1", "C1"),
        _edge("s3", "P2", "C2"),
    ]
    result = identify_families(edges, _KINDS)
    assert len(result.families) == 1
    fam = result.families[0]
    assert fam.family_id == "P1"  # 排序最小控制人
    assert fam.controllers == ("P1", "P2")
    assert {m.entity_id for m in fam.members} == {"P1", "P2", "C1", "C2"}


def test_cross_holding_cycle_merges_families() -> None:
    """交叉持股环并族：P1→C1、P2→C2，C1⇄C2 互持过半 → 环上实体同族 → 两族合并。"""
    edges = [
        _edge("s1", "P1", "C1"),
        _edge("s2", "P2", "C2"),
        _edge("s3", "C1", "C2", predicate="holds_shares", share=60 * 10**6),
        _edge("s4", "C2", "C1", predicate="holds_shares", share=55 * 10**6),
    ]
    result = identify_families(edges, _KINDS)
    assert len(result.families) == 1
    fam = result.families[0]
    assert fam.controllers == ("P1", "P2")
    assert {m.entity_id for m in fam.members} == {"P1", "P2", "C1", "C2"}
    assert fam.cycle_count == 1  # C1→C2→C1 环路


def test_component_without_controller_is_unassigned() -> None:
    """无控制人的连通分量不成族：公司互相过半持股但无自然人/国资根 → 显式计数。"""
    edges = [
        _edge("s1", "C1", "C2", predicate="holds_shares", share=60 * 10**6),
        _edge("s2", "C2", "C1", predicate="holds_shares", share=60 * 10**6),
    ]
    result = identify_families(edges, _KINDS)
    assert result.families == ()
    assert result.unassigned_entity_count == 2


def test_unknown_kind_entity_is_not_a_root() -> None:
    """kind 未知的实体保守地不作为控制人根。"""
    edges = [_edge("s1", "X1", "C1")]
    result = identify_families(edges, {"X1": "mystery", "C1": "company"})
    assert result.families == ()
    assert result.unassigned_entity_count == 2


def test_enterprise_subject_is_not_a_root() -> None:
    """企业主体不作为族根（根必须是非企业实体）。"""
    edges = [
        _edge("s1", "C4", "C1", predicate="holds_shares", share=90 * 10**6),
        _edge("s2", "C4", "C2", predicate="holds_shares", share=90 * 10**6),
    ]
    result = identify_families(edges, _KINDS)
    assert result.families == ()
    assert result.unassigned_entity_count == 3


def test_family_stats_density_regions_cycles() -> None:
    """族内持股密度、跨省成员分布与族内环路数。"""
    edges = [
        _edge("s1", "P1", "C1"),
        _edge("s2", "P1", "C2"),
        _edge("s3", "C1", "C2", predicate="holds_shares", share=60 * 10**6),
        _edge("s4", "C2", "C1", predicate="holds_shares", share=60 * 10**6),
    ]
    kinds = {**_KINDS, "C1": "company", "C2": "company"}
    region = {"P1": None, "C1": "110000", "C2": "310000"}
    result = identify_families(edges, kinds, region_by_entity=region)
    fam = result.families[0]
    # 内部控制类边 4 条；n=3 → density = 4/(3*2)
    assert fam.internal_edge_count == 4
    assert fam.density is not None and abs(fam.density - 4 / 6) < 1e-6
    assert fam.region_distribution == (("110000", 1), ("310000", 1))
    assert fam.region_unknown == 1
    assert fam.cycle_count == 1
    assert result.families[0].member_count == 3


def test_minimal_family_density() -> None:
    """最小族（1 控制边）：2 成员，密度 = 1/(2*1) = 0.5；n<2 无定义分支仅为防御。"""
    edges = [_edge("s1", "P1", "C1")]
    result = identify_families(edges, _KINDS)
    fam = result.families[0]
    assert fam.member_count == 2
    assert fam.density == 0.5
    # n<2 时密度无定义（identify_families 不会产出，数据类层面防御为 None）
    defensive = Family(
        family_id="X",
        controllers=("X",),
        members=(),
        internal_edge_count=0,
        density=None,
        region_distribution=(),
        region_unknown=0,
        cycle_count=0,
    )
    assert defensive.density is None and defensive.member_count == 0


def test_member_guardrail_caps_traversal() -> None:
    """护栏：单族成员上限命中后停止扩展并标记 truncated（结果仍确定）。"""
    edges = [
        _edge("s1", "P1", "C1"),
        _edge("s2", "C1", "C2", predicate="holds_shares", share=60 * 10**6),
        _edge("s3", "C2", "C3", predicate="holds_shares", share=60 * 10**6),
    ]
    cfg = FamiliesConfig(max_members_per_family=2)
    result = identify_families(edges, _KINDS, cfg)
    fam = result.families[0]
    assert {m.entity_id for m in fam.members} == {"P1", "C1"}
    assert fam.truncated is True


def test_deterministic_same_input_same_output() -> None:
    """确定性：同输入两次运行全等；输入顺序打乱不影响结果。"""
    edges = [
        _edge("s1", "P2", "C2"),
        _edge("s2", "P1", "C1"),
        _edge("s3", "C1", "C2", predicate="holds_shares", share=60 * 10**6),
        _edge("s4", "P2", "C3"),
    ]
    a = identify_families(edges, _KINDS)
    b = identify_families(list(reversed(edges)), _KINDS)
    assert a == b


def test_config_hash_reflects_threshold() -> None:
    """配置哈希随阈值变化，可复现口径留痕。"""
    h1 = FamiliesConfig().canonical_hash()
    h2 = FamiliesConfig(min_control_ratio_percent=30.0).canonical_hash()
    assert h1 != h2
    assert len(h1) == 64
    assert FAMILIES_ALGORITHM_VERSION.startswith("cg-families/")


def test_family_flows_grouping() -> None:
    """族间资本流向：按族对聚合金额；同族边与无族边显式计数。"""
    family_by_entity = {"C1": "P1", "C2": "P1", "C3": "P2"}
    edges = [
        FlowEdge(
            statement_id="f1",
            from_region="110000",
            to_region="310000",
            object_id="C2",
            subject_id="C1",
            ratio_scaled=60 * 10**6,
            amount_scaled=10000,  # 100 万元
            year=2020,
        ),
        FlowEdge(
            statement_id="f2",
            from_region="110000",
            to_region="310000",
            object_id="C2",
            subject_id="C1",
            ratio_scaled=60 * 10**6,
            amount_scaled=5000,  # 50 万元
            year=2021,
        ),
        FlowEdge(
            statement_id="f3",
            from_region="110000",
            to_region="330000",
            object_id="C3",
            subject_id="C1",
            ratio_scaled=None,
            amount_scaled=None,
            year=2021,
        ),
        FlowEdge(
            statement_id="f4",
            from_region="110000",
            to_region="310000",
            object_id="C2",
            subject_id="C1",  # 族内边：C1、C2 同属 P1 族
            ratio_scaled=None,
            amount_scaled=999,
            year=2021,
        ),
        FlowEdge(
            statement_id="f5",
            from_region="110000",
            to_region="440000",
            object_id="C9",  # 无族实体
            subject_id="C1",
            ratio_scaled=None,
            amount_scaled=1,
            year=2021,
        ),
    ]
    result = family_flows(edges, family_by_entity)
    # f1/f2 同为 P1→P1（C1→C2 都属 P1 族）→ 族内；f3: P1→P2 跨族
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["from_family"] == "P1"
    assert row["to_family"] == "P2"
    assert row["edge_count"] == 1
    assert row["amount_wan"] is None  # 缺失金额，绝不补值
    assert row["amount_missing_edges"] == 1
    assert result["intra_family_edges"] == 3  # f1 f2 f4
    assert result["ungrouped_edges"] == 1  # f5
