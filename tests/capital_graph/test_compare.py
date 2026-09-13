"""格局对比纯函数单测（切片 B）：families diff 与区域流动对比。

口径：对比 = 两个时点各自完整重算结果的集合差异；缺损失配对差值显式 None；
输出全排序、同输入同输出；不改变 families/flows 既有函数的签名与行为。
"""

from __future__ import annotations

from cg_capital_graph import (
    FamiliesConfig,
    FamiliesResult,
    Family,
    FlowEdge,
    MemberInfo,
    compare_flows,
    diff_families,
)


def family(
    fid: str,
    members: tuple[str, ...],
    controllers: tuple[str, ...] | None = None,
    cycles: int = 0,
    regions: tuple[tuple[str, int], ...] = (),
) -> Family:
    ctrls = controllers or (fid,)
    return Family(
        family_id=fid,
        controllers=ctrls,
        members=tuple(
            MemberInfo(
                entity_id=m, controller=ctrls[0], path=(ctrls[0], m), statement_ids=("s",), depth=1
            )
            for m in members
        ),
        internal_edge_count=len(members),
        density=None,
        region_distribution=regions,
        region_unknown=0,
        cycle_count=cycles,
    )


def result(*fams: Family, unassigned: int = 0) -> FamiliesResult:
    return FamiliesResult(
        families=tuple(fams),
        unassigned_entity_count=unassigned,
        missing_ratio_holding_edges=0,
        config_hash=FamiliesConfig().canonical_hash(),
    )


# ---------------------------------------------------------------- families diff


def test_families_diff_identical_results_unchanged():
    a = result(family("P1", ("P1", "C1", "C2")))
    d = diff_families(a, a)
    assert d["added_family_ids"] == []
    assert d["removed_family_ids"] == []
    assert d["changed"] == []
    assert d["unchanged_count"] == 1


def test_families_diff_added_and_removed():
    before = result(family("P1", ("P1", "C1")))
    after = result(family("P2", ("P2", "C2")))
    d = diff_families(before, after)
    assert d["added_family_ids"] == ["P2"]
    assert d["removed_family_ids"] == ["P1"]
    assert d["changed"] == []
    assert d["family_count"] == {"before": 1, "after": 1, "delta": 0}


def test_families_diff_member_and_controller_changes():
    before = result(family("P1", ("P1", "C1", "C2"), controllers=("P1",)))
    after = result(family("P1", ("P1", "C1", "C3"), controllers=("P1", "P9"), cycles=1))
    d = diff_families(before, after)
    assert len(d["changed"]) == 1
    row = d["changed"][0]
    assert row["family_id"] == "P1"
    assert row["members_added"] == ["C3"]
    assert row["members_removed"] == ["C2"]
    assert row["controllers_added"] == ["P9"]
    assert row["controllers_removed"] == []
    assert row["member_count_before"] == 3
    assert row["member_count_after"] == 3
    assert row["cycle_count_before"] == 0
    assert row["cycle_count_after"] == 1


def test_families_diff_deterministic_ordering():
    before = result(family("P1", ("P1", "C1")), family("P2", ("P2", "C2")))
    after = result(family("P0", ("P0", "C0")), family("P3", ("P3", "C3")))
    d1 = diff_families(before, after)
    d2 = diff_families(list(before.families) and before, after)
    assert d1 == d2
    assert d1["added_family_ids"] == sorted(d1["added_family_ids"])


def test_families_diff_member_controller_path_change():
    # 成员集合不变、族控制器不变，但成员的被控路径归属变化（控制权族内移动）→ changed
    before = result(
        Family(
            family_id="P1",
            controllers=("P1", "P2"),
            members=(
                MemberInfo("P1", "P1", ("P1",), (), 0),
                MemberInfo("P2", "P2", ("P2",), (), 0),
                MemberInfo("C1", "P1", ("P1", "C1"), ("s1",), 1),
            ),
            internal_edge_count=2,
            density=None,
            region_distribution=(),
            region_unknown=0,
            cycle_count=0,
        )
    )
    after = result(
        Family(
            family_id="P1",
            controllers=("P1", "P2"),
            members=(
                MemberInfo("P1", "P1", ("P1",), (), 0),
                MemberInfo("P2", "P2", ("P2",), (), 0),
                MemberInfo("C1", "P2", ("P2", "C1"), ("s2",), 1),
            ),
            internal_edge_count=2,
            density=None,
            region_distribution=(),
            region_unknown=0,
            cycle_count=0,
        )
    )
    d = diff_families(before, after)
    assert len(d["changed"]) == 1
    row = d["changed"][0]
    assert row["path_changed"] == [
        {"member": "C1", "controller_before": "P1", "controller_after": "P2"}
    ]


def test_families_diff_unassigned_count_delta():
    before = result(family("P1", ("P1", "C1")), unassigned=2)
    after = result(family("P1", ("P1", "C1")), unassigned=5)
    d = diff_families(before, after)
    assert d["unassigned_entity_count"] == {"before": 2, "after": 5, "delta": 3}


# ---------------------------------------------------------------- flows compare


def edge(sid: str, src: str, dst: str, amount: int | None, year: int = 2020) -> FlowEdge:
    return FlowEdge(
        statement_id=sid,
        from_region=src,
        to_region=dst,
        object_id=f"obj-{sid}",
        ratio_scaled=None,
        amount_scaled=amount,
        year=year,
        subject_id=f"sub-{sid}",
    )


def test_flows_compare_identical_edges_zero_delta():
    edges = [edge("1", "110000", "310000", 500000), edge("2", "110000", "440000", 300000)]
    d = compare_flows(edges, list(edges))
    assert d["totals"]["flow_count"]["delta"] == 0
    assert d["totals"]["total_cross_amount_wan"]["delta"] == 0.0
    assert d["flows_added"] == []
    assert d["flows_removed"] == []
    assert d["flows_changed"] == []
    assert d["flow_pair_delta_check"] is True


def test_flows_compare_added_removed_and_changed_pairs():
    before = [edge("1", "110000", "310000", 500000), edge("2", "110000", "440000", 300000)]
    after = [edge("3", "110000", "310000", 700000), edge("4", "320000", "310000", 100000)]
    d = compare_flows(before, after)
    assert d["flows_added"] == [
        {
            "from_region": "320000",
            "to_region": "310000",
            "edge_count": 1,
            "amount_edges": 1,
            "amount_wan": 1000.0,
            "total_share_percent": None,
            "ratio_missing_edges": 1,
        }
    ]
    assert [(r["from_region"], r["to_region"]) for r in d["flows_removed"]] == [
        ("110000", "440000")
    ]
    assert len(d["flows_changed"]) == 1
    ch = d["flows_changed"][0]
    assert (ch["from_region"], ch["to_region"]) == ("110000", "310000")
    assert ch["amount_before_wan"] == 5000.0
    assert ch["amount_after_wan"] == 7000.0
    assert ch["amount_delta_wan"] == 2000.0
    assert d["totals"]["flow_count"]["delta"] == 0
    # 前 5000+3000=8000 万；后 7000+1000=8000 万 → 总额差值 0
    assert d["totals"]["total_cross_amount_wan"]["delta"] == 0.0
    assert d["flow_pair_delta_check"] is True


def test_flows_compare_hhi_delta_and_none_safe():
    # 全部流出集中在一个省 → HHI = 10000；两侧同构 → delta 0
    edges = [edge("1", "110000", "310000", 500000)]
    d = compare_flows(edges, list(edges))
    assert d["totals"]["hhi"] == {"before": 10000.0, "after": 10000.0, "delta": 0.0}
    # 一侧无任何流动 → HHI before None → delta None（缺失显式，不补值）
    d2 = compare_flows([], [edge("9", "110000", "310000", 100000)])
    assert d2["totals"]["hhi"]["before"] is None
    assert d2["totals"]["hhi"]["delta"] is None


def test_flows_compare_deterministic():
    before = [edge("1", "110000", "310000", 500000), edge("2", "330000", "440000", 1)]
    after = [edge("3", "110000", "310000", 900000), edge("4", "510000", "320000", 2)]
    a = compare_flows(before, after)
    b = compare_flows(list(reversed(before)), list(reversed(after)))
    assert a == b
