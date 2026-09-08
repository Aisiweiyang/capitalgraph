"""穿透引擎与分析测试：链式持股、环路、缺比例、确定性、护栏。"""

from datetime import date

import pytest
from fractions import Fraction

from cg_capital_graph import (
    GraphEdge,
    PenetrationTimeout,
    aggregate_by_shareholder,
    analyse,
    cross_holdings,
    detect_cycles,
    penetrate,
    result_to_jsonable,
    ubo_candidates,
)
from cg_domain.models import PenetrationConfig
from cg_domain.orm import RATIO_SCALE


def pct(scaled: int | None) -> float | None:
    return None if scaled is None else round(scaled * 100.0 / RATIO_SCALE, 6)


def edge(sid: str, s: str, o: str, share: float | None, voting: float | None = None) -> GraphEdge:
    return GraphEdge(
        statement_id=sid,
        subject=s,
        obj=o,
        predicate="holds_shares",
        share_scaled=None if share is None else round(share * RATIO_SCALE / 100),
        voting_scaled=None if voting is None else round(voting * RATIO_SCALE / 100),
    )


CFG = PenetrationConfig(direction="up", max_depth=6, min_ratio_percent=0.01)


def test_simple_chain_two_levels():
    # 张三 →甲公司 60%；甲公司 → 目标 100%
    edges = [
        edge("s1", "zhang", "jia", 60.0),
        edge("s2", "jia", "target", 100.0),
    ]
    result = penetrate("target", edges, CFG)
    agg = {a.entity_id: a for a in aggregate_by_shareholder(result)}
    assert pct(agg["zhang"].effective_scaled) == 60.0
    assert pct(agg["jia"].effective_scaled) == 100.0
    assert agg["jia"].direct_scaled is not None
    assert agg["zhang"].direct_scaled is None  # 间接持股 direct 为空


def test_multi_path_aggregation_sums_products():
    # 张三 →甲 50%、张三 →乙 40%、甲→目标 60%、乙→目标 50%
    # 有效权益 = 0.5*0.6 + 0.4*0.5 = 0.5
    edges = [
        edge("s1", "zhang", "jia", 50.0),
        edge("s2", "zhang", "yi", 40.0),
        edge("s3", "jia", "target", 60.0),
        edge("s4", "yi", "target", 50.0),
    ]
    result = penetrate("target", edges, CFG)
    agg = {a.entity_id: a for a in aggregate_by_shareholder(result)}
    assert abs(pct(agg["zhang"].effective_scaled) - 50.0) < 1e-6


def test_cycle_detection_no_infinite_recursion():
    edges = [
        edge("s1", "a", "target", 100.0),
        edge("s2", "b", "a", 50.0),
        edge("s3", "a", "b", 30.0),  # a↔b 环
    ]
    result = penetrate("target", edges, CFG)
    cycles = detect_cycles(edges)
    assert len(cycles) == 1
    # a 的权益：直接 100%（环上路径不重复枚举，简单路径原则）
    agg = {x.entity_id: x for x in aggregate_by_shareholder(result)}
    assert pct(agg["a"].effective_scaled) == 100.0
    assert pct(agg["b"].effective_scaled) == 50.0  # b→a→target = 50%*100%


def test_missing_ratio_flagged_not_fabricated():
    edges = [edge("s1", "zhang", "target", None)]
    result = penetrate("target", edges, CFG)
    agg = {x.entity_id: x for x in aggregate_by_shareholder(result)}
    assert agg["zhang"].effective_scaled == 0
    assert agg["zhang"].via_missing_ratio is True
    payload = result_to_jsonable(analyse("target", result, edges, CFG), result)
    zhang = next(a for a in payload["aggregates"] if a["entity_id"] == "zhang")
    assert zhang["effective_percent"] == 0.0
    assert zhang["unknown_ratio"] is True


def test_min_ratio_prunes_dust_paths():
    edges = [
        edge("s1", "big", "target", 50.0),
        edge("s2", "tiny", "mid", 0.001),
        edge("s3", "mid", "target", 0.001),
    ]
    result = penetrate("target", edges, PenetrationConfig(direction="up", min_ratio_percent=0.01))
    agg_ids = {a.entity_id for a in aggregate_by_shareholder(result)}
    assert "big" in agg_ids
    assert "tiny" not in agg_ids  # 0.001% * 0.001% 远低于阈值


def test_determinism_same_input_same_output():
    edges = [
        edge("s1", "p1", "t", 30.0),
        edge("s2", "p2", "t", 20.0),
        edge("s3", "p3", "t", 55.0),
        edge("s4", "p1", "p2", 10.0),
    ]
    result1 = penetrate("t", edges, CFG)
    result2 = penetrate("t", edges, CFG)
    r1 = result_to_jsonable(analyse("t", result1, edges, CFG), result1)
    r2 = result_to_jsonable(analyse("t", result2, edges, CFG), result2)
    assert r1 == r2
    assert r1["config_hash"] == r2["config_hash"]


def test_path_cap_marks_truncated():
    # 构造 3 层二叉树使路径数超上限
    edges = []
    node_seq = 0

    def new_node() -> str:
        nonlocal node_seq
        node_seq += 1
        return f"n{node_seq}"

    level = ["t"]
    for _depth in range(4):
        nxt = []
        for node in level:
            for _ in range(2):
                child = new_node()
                edges.append(edge(f"s{child}", child, node, 10.0))
                nxt.append(child)
        level = nxt
    result = penetrate("t", edges, PenetrationConfig(direction="up", max_paths=10))
    assert result.truncated


def test_timeout_raises_not_partial():
    class FakeClock:
        def __init__(self) -> None:
            self.t = 0.0

        def __call__(self) -> float:
            self.t += 1.0
            return self.t

    edges = [edge("s1", "a", "t", 100.0)]
    with pytest.raises(PenetrationTimeout):
        penetrate(
            "t",
            edges,
            PenetrationConfig(direction="up", timeout_seconds=0.001),
            monotonic=FakeClock(),
        )


def test_cross_holdings_pair():
    edges = [
        edge("s1", "a", "b", 30.0),
        edge("s2", "b", "a", 25.0),
        edge("s3", "c", "a", 10.0),
    ]
    pairs = cross_holdings(edges)
    found = {(p.entity_a, p.entity_b) for p in pairs}
    assert ("a", "b") in found
    assert all("c" not in pair for pair in found)


def test_ubo_rule_major_shareholder():
    # 张三直接 60% → 必为候选；李四 5% → 不是
    edges = [edge("s1", "zhang", "t", 60.0), edge("s2", "li", "t", 5.0)]
    result = penetrate("t", edges, CFG)
    ubo = ubo_candidates(result, edges, min_effective_percent=25.0)
    ids = [c.entity_id for c in ubo]
    assert "zhang" in ids
    assert "li" not in ids
    assert all(c.basis for c in ubo)


def test_ubo_via_control_statement():
    # 王五只有 10% 持股但有显式控制声明 → R2 候选
    edges = [
        edge("s1", "wang", "t", 10.0),
        GraphEdge(
            statement_id="s2",
            subject="wang",
            obj="t",
            predicate="controls",
            share_scaled=None,
            voting_scaled=None,
        ),
    ]
    result = penetrate("t", edges, CFG)
    ubo = ubo_candidates(result, edges, min_effective_percent=25.0)
    wang = [c for c in ubo if c.entity_id == "wang"]
    assert len(wang) == 1
    assert any("R2" in b for b in wang[0].basis)
    assert wang[0].has_control_statement


def test_assumptions_always_documented():
    edges = [edge("s1", "a", "t", 100.0)]
    result = penetrate("t", edges, CFG)
    payload = result_to_jsonable(analyse("t", result, edges, CFG), result)
    assert payload["assumptions"]
    assert payload["algorithm_version"].startswith("cg-penetration/")
