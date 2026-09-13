"""格局对比：系族与区域资本流动两个时点的差异（纯函数、确定性、无 IO）。

口径（ADR-017 增补）：
- 输入为两个时点各自的系族识别结果 / 流动边集合（时点过滤由仓储与识别函数完成），
  本层只做结果集合对比，不改变 families/flows 既有函数的签名与行为；
- families diff：族出现/消失（按族 ID）、控制人增减、成员增减清单、
  规模/省份覆盖/环路数变化；全部键与清单排序输出，同输入同输出；
- 区域对比：跨省金额、HHI、流向条数的两时点差值，以及新增/消失/变化的流向对；
  任一侧金额缺失（None）时差值显式为 None，绝不补值（沿 ADR-014 金额口径）；
- 结果为算法候选，仅供研究参考。
"""

from __future__ import annotations

from cg_capital_graph.flows import FlowEdge, RegionFlow, aggregate_flows, region_summary

COMPARE_ALGORITHM_VERSION = "cg-compare/1.0.0"

COMPARE_ASSUMPTIONS: tuple[str, ...] = (
    "对比 = 两个时点各自完整重算后的结果集合差异；时点内口径与单时点算法一致；",
    "族 ID = 族内控制人集合排序最小者，跨时点按 ID 对齐；",
    "金额/HHI 差值仅在两侧齐备时给出，任一侧缺失显式为 None，绝不补值；",
    "对比结果为算法候选，仅供研究参考，不构成法律认定或投资建议。",
)


def _delta(before: float | None, after: float | None) -> dict:
    d = round(after - before, 6) if before is not None and after is not None else None
    return {"before": before, "after": after, "delta": d}


def diff_families(before, after) -> dict:
    """系族格局对比。before/after 为 FamiliesResult（同阈值口径）。

    changed 判定 = 控制人集合、成员集合、环路数或省份覆盖任一变化；
    全部输出按 ID/代码排序，确定性可复现。
    """
    before_by = {f.family_id: f for f in before.families}
    after_by = {f.family_id: f for f in after.families}
    added_ids = sorted(set(after_by) - set(before_by))
    removed_ids = sorted(set(before_by) - set(after_by))
    changed = []
    common = sorted(set(before_by) & set(after_by))
    for fid in common:
        b, a = before_by[fid], after_by[fid]
        b_members = {m.entity_id for m in b.members}
        a_members = {m.entity_id for m in a.members}
        b_ctrl, a_ctrl = set(b.controllers), set(a.controllers)
        # 成员级被控路径归属：同一成员的首达控制人变化 = 控制权在族内移动
        b_by_member = {m.entity_id: m.controller for m in b.members}
        a_by_member = {m.entity_id: m.controller for m in a.members}
        path_changed = [
            {
                "member": eid,
                "controller_before": b_by_member[eid],
                "controller_after": a_by_member[eid],
            }
            for eid in sorted(set(b_by_member) & set(a_by_member))
            if b_by_member[eid] != a_by_member[eid]
        ]
        if (
            b_members == a_members
            and b_ctrl == a_ctrl
            and b.cycle_count == a.cycle_count
            and b.region_coverage == a.region_coverage
            and not path_changed
        ):
            continue
        changed.append(
            {
                "family_id": fid,
                "controllers_added": sorted(a_ctrl - b_ctrl),
                "controllers_removed": sorted(b_ctrl - a_ctrl),
                "members_added": sorted(a_members - b_members),
                "members_removed": sorted(b_members - a_members),
                "path_changed": path_changed,
                "member_count_before": b.member_count,
                "member_count_after": a.member_count,
                "region_coverage_before": b.region_coverage,
                "region_coverage_after": a.region_coverage,
                "cycle_count_before": b.cycle_count,
                "cycle_count_after": a.cycle_count,
            }
        )
    return {
        "algorithm_version": COMPARE_ALGORITHM_VERSION,
        "family_count": {
            "before": len(before.families),
            "after": len(after.families),
            "delta": len(after.families) - len(before.families),
        },
        "added_family_ids": added_ids,
        "removed_family_ids": removed_ids,
        "changed": changed,
        "unchanged_count": len(common) - len(changed),
        "unassigned_entity_count": {
            "before": before.unassigned_entity_count,
            "after": after.unassigned_entity_count,
            "delta": after.unassigned_entity_count - before.unassigned_entity_count,
        },
        "assumptions": COMPARE_ASSUMPTIONS,
    }


def _flow_row(f: RegionFlow) -> dict:
    return {
        "from_region": f.from_region,
        "to_region": f.to_region,
        "edge_count": f.edge_count,
        "amount_edges": f.amount_edges,
        "amount_wan": f.amount_wan,
        "total_share_percent": f.total_share_percent,
        "ratio_missing_edges": f.ratio_missing_edges,
    }


def compare_flows(before: list[FlowEdge], after: list[FlowEdge]) -> dict:
    """区域资本流动格局对比：总量指标差值 + 流向对新增/消失/变化。"""
    before_flows = {(f.from_region, f.to_region): f for f in aggregate_flows(before)}
    after_flows = {(f.from_region, f.to_region): f for f in aggregate_flows(after)}
    before_summary = region_summary(before)
    after_summary = region_summary(after)

    added_keys = sorted(set(after_flows) - set(before_flows))
    removed_keys = sorted(set(before_flows) - set(after_flows))
    changed = []
    for key in sorted(set(before_flows) & set(after_flows)):
        b, a = before_flows[key], after_flows[key]
        if b.edge_count == a.edge_count and b.amount_wan == a.amount_wan:
            continue
        changed.append(
            {
                "from_region": key[0],
                "to_region": key[1],
                "edge_count_before": b.edge_count,
                "edge_count_after": a.edge_count,
                "amount_before_wan": b.amount_wan,
                "amount_after_wan": a.amount_wan,
                "amount_delta_wan": (
                    round(a.amount_wan - b.amount_wan, 2)
                    if b.amount_wan is not None and a.amount_wan is not None
                    else None
                ),
            }
        )

    hhi_before = before_summary["hhi"]
    hhi_after = after_summary["hhi"]
    return {
        "algorithm_version": COMPARE_ALGORITHM_VERSION,
        "totals": {
            "flow_count": {
                "before": before_summary["flow_count"],
                "after": after_summary["flow_count"],
                "delta": after_summary["flow_count"] - before_summary["flow_count"],
            },
            "total_cross_amount_wan": {
                "before": before_summary["total_cross_amount_wan"],
                "after": after_summary["total_cross_amount_wan"],
                "delta": round(
                    after_summary["total_cross_amount_wan"]
                    - before_summary["total_cross_amount_wan"],
                    2,
                ),
            },
            "hhi": _delta(hhi_before, hhi_after),
        },
        "flows_added": [_flow_row(after_flows[k]) for k in added_keys],
        "flows_removed": [_flow_row(before_flows[k]) for k in removed_keys],
        "flows_changed": changed,
        "flow_pair_delta_check": (
            len(after_flows) - len(before_flows) == len(added_keys) - len(removed_keys)
        ),
        "assumptions": COMPARE_ASSUMPTIONS,
    }
