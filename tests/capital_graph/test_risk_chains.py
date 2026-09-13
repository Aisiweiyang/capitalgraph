"""担保链/担保环/风险传导纯函数单测：口径、缺失显式处理、确定性。

口径（ADR-016）：
- 担保边 provides_guarantee：subject=担保人（出险时代偿），object=被担保人；
- 链条沿"义务方向"（被担保人 → 担保人）回溯：下游出险 → 上游担保人受累；
- 环 = 声明方向（担保人 → 被担保人）上的环路，即互保圈；输出规范化（最小节点起头）；
- 传导：出险集合沿义务方向逐层扩散；层内名义金额 = 引发该层的担保边金额合计，
  任一边缺金额 → 该层 nominal=None + 缺失计数；合计仅在全部金额齐备时输出，绝不补值。
"""

from __future__ import annotations

from cg_capital_graph.risk_chains import (
    RISK_CHAINS_ALGORITHM_VERSION,
    GuaranteeEdge,
    RiskChainsConfig,
    canonicalize_cycles,
    guarantee_chains,
    guarantee_cycles,
    input_digest,
    propagate_risk,
)


def _ge(sid: str, guarantor: str, beneficiary: str, amount: int | None) -> GuaranteeEdge:
    return GuaranteeEdge(
        statement_id=sid, guarantor=guarantor, beneficiary=beneficiary, amount_scaled=amount
    )


def test_chain_follows_obligation_direction() -> None:
    """A 担保 B、B 担保 C：从 C 出发的链条 = C→B→A（义务方向）。"""
    edges = [
        _ge("g1", "A", "B", 10_000),
        _ge("g2", "B", "C", 8_000),
    ]
    chains = guarantee_chains(edges, "C")
    paths = [c.path for c in chains]
    assert ("C", "B") in paths
    assert ("C", "B", "A") in paths
    full = next(c for c in chains if c.path == ("C", "B", "A"))
    assert full.statement_ids == ("g2", "g1")
    assert full.nominal_amount_scaled == 18_000
    assert full.amount_missing_edges == 0


def test_chain_from_head_is_empty() -> None:
    """链顶担保人 A：义务方向上无人为 A 担保 → 无链条；B 出发则指向 A。"""
    edges = [
        _ge("g1", "A", "B", 10_000),
        _ge("g2", "B", "C", 8_000),
    ]
    assert guarantee_chains(edges, "A") == []
    chains_b = guarantee_chains(edges, "B")
    assert [c.path for c in chains_b] == [("B", "A")]


def test_cycle_detection_and_canonicalization() -> None:
    """互保圈 A→B→C→A 检出 1 环，规范化输出（最小节点起头，去重）。"""
    edges = [
        _ge("g1", "A", "B", 5_000),
        _ge("g2", "B", "C", 5_000),
        _ge("g3", "C", "A", 5_000),
        _ge("g4", "C", "A", 5_000),  # 重复边不产生第二个环
    ]
    cycles = guarantee_cycles(edges)
    assert cycles == [("A", "B", "C", "A")]


def test_canonicalize_cycle_rotation() -> None:
    """环规范化：旋转到最小节点起头，反向环视为同一环。"""
    assert canonicalize_cycles([["B", "C", "A", "B"]]) == [("A", "B", "C", "A")]
    assert canonicalize_cycles([["C", "B", "A", "C"]]) == [("A", "C", "B", "A")]
    assert canonicalize_cycles([["A", "B", "A"]]) == [("A", "B", "A")]


def test_propagation_along_chain_with_amounts() -> None:
    """C 出险：第 1 层 B（名义 8000），第 2 层 A（名义 10000），合计 18000。"""
    edges = [
        _ge("g1", "A", "B", 10_000),
        _ge("g2", "B", "C", 8_000),
    ]
    prop = propagate_risk(edges, {"C"})
    assert prop.origin == ("C",)
    assert prop.affected_entities == ("A", "B")  # 排序输出；传导顺序看 levels
    assert prop.levels[0].newly_affected == ("B",)
    assert prop.levels[0].nominal_amount_scaled == 8_000
    assert prop.levels[1].newly_affected == ("A",)
    assert prop.levels[1].nominal_amount_scaled == 10_000
    assert prop.total_nominal_scaled == 18_000
    assert prop.total_amount_missing_edges == 0


def test_propagation_missing_amount_is_explicit() -> None:
    """缺失金额边：该层 nominal=None + 缺失计数；合计为 None，绝不补值。"""
    edges = [
        _ge("g1", "A", "B", None),
        _ge("g2", "B", "C", 8_000),
    ]
    prop = propagate_risk(edges, {"C"})
    assert prop.levels[0].nominal_amount_scaled == 8_000
    assert prop.levels[1].nominal_amount_scaled is None
    assert prop.levels[1].amount_missing_edges == 1
    assert prop.total_nominal_scaled is None
    assert prop.total_amount_missing_edges == 1


def test_propagation_through_mutual_guarantee_ring() -> None:
    """互保圈一点出险全圈受累：B 出险 → A → C，无重复计数。"""
    edges = [
        _ge("g1", "A", "B", 1_000),
        _ge("g2", "B", "C", 2_000),
        _ge("g3", "C", "A", 3_000),
    ]
    prop = propagate_risk(edges, {"B"})
    assert prop.affected_entities == ("A", "C")
    assert prop.total_nominal_scaled == 4_000  # g1 (B 受累) + g3 (C 受累)
    assert prop.levels[0].newly_affected == ("A",)
    assert prop.levels[1].newly_affected == ("C",)


def test_propagation_respects_depth_bound() -> None:
    """深度护栏：max_depth=1 时只扩散一层。"""
    edges = [
        _ge("g1", "A", "B", 10_000),
        _ge("g2", "B", "C", 8_000),
    ]
    prop = propagate_risk(edges, {"C"}, RiskChainsConfig(max_depth=1))
    assert prop.affected_entities == ("B",)
    assert len(prop.levels) == 1


def test_chains_and_propagation_deterministic() -> None:
    """确定性：乱序输入两次运行结果全等。"""
    edges = [
        _ge("g1", "A", "B", 10_000),
        _ge("g2", "B", "C", 8_000),
        _ge("g3", "C", "A", 5_000),
    ]
    a = (guarantee_chains(edges, "C"), guarantee_cycles(edges), propagate_risk(edges, {"C"}))
    b = (
        guarantee_chains(list(reversed(edges)), "C"),
        guarantee_cycles(list(reversed(edges))),
        propagate_risk(list(reversed(edges)), {"C"}),
    )
    assert a == b


def test_input_digest_and_versions() -> None:
    """输入摘要对边集内容敏感（与顺序无关）；版本号可追溯。"""
    e1 = [_ge("g1", "A", "B", 10_000), _ge("g2", "B", "C", 8_000)]
    e2 = [_ge("g2", "B", "C", 8_000), _ge("g1", "A", "B", 10_000)]
    assert input_digest(e1) == input_digest(e2)
    assert input_digest(e1) != input_digest(e1[:-1])
    assert len(input_digest(e1)) == 64
    assert RISK_CHAINS_ALGORITHM_VERSION.startswith("cg-risk-chains/")
    assert len(RiskChainsConfig().canonical_hash()) == 64
