"""跨区域流动聚合纯函数测试：口径正确性、缺失值处理、确定性。"""

from __future__ import annotations

from cg_capital_graph import (
    FlowEdge,
    aggregate_flows,
    flow_timeline,
    industry_flows,
    region_summary,
)

AMOUNT_SCALE = 100  # 万元×100


def edge(
    sid: str,
    src: str,
    dst: str,
    *,
    amount_wan: float | None = 1000.0,
    ratio: float | None = 50.0,
    year: int = 2018,
    obj: str = "O",
) -> FlowEdge:
    return FlowEdge(
        statement_id=sid,
        from_region=src,
        to_region=dst,
        object_id=obj,
        ratio_scaled=None if ratio is None else round(ratio * 10**6),
        amount_scaled=None if amount_wan is None else round(amount_wan * AMOUNT_SCALE),
        year=year,
    )


def test_cross_region_excludes_same_province():
    edges = [edge("1", "110000", "310000"), edge("2", "110000", "110000")]
    flows = aggregate_flows(edges)
    assert len(flows) == 1
    assert (flows[0].from_region, flows[0].to_region) == ("110000", "310000")


def test_aggregation_merges_parallel_edges_and_sums():
    flows = aggregate_flows(
        [
            edge("1", "110000", "310000", amount_wan=1000.0, ratio=10.0),
            edge("2", "110000", "310000", amount_wan=2500.5, ratio=20.0),
            edge("3", "110000", "310000", amount_wan=None, ratio=None),
        ]
    )
    f = flows[0]
    assert f.edge_count == 3
    assert f.amount_edges == 2
    assert f.amount_wan == 3500.5
    assert f.total_share_percent == 30.0
    assert f.ratio_missing_edges == 1


def test_amount_missing_stays_none_not_zero():
    flows = aggregate_flows([edge("1", "440000", "110000", amount_wan=None)])
    assert flows[0].amount_wan is None
    assert flows[0].amount_edges == 0


def test_min_amount_filters_low_and_missing():
    flows = aggregate_flows(
        [
            edge("1", "110000", "310000", amount_wan=50.0),
            edge("2", "110000", "440000", amount_wan=500.0),
            edge("3", "110000", "120000", amount_wan=None),
        ],
        min_amount_wan=100.0,
    )
    assert [(f.to_region, f.amount_wan) for f in flows] == [("440000", 500.0)]


def test_summary_inflow_outflow_net_and_internal():
    summary = region_summary(
        [
            edge("1", "110000", "310000", amount_wan=1000.0),
            edge("2", "310000", "110000", amount_wan=300.0),
            edge("3", "110000", "110000", amount_wan=999.0),  # 省内
            edge("4", "110000", "330000", amount_wan=None),  # 无金额边仍计流向
        ]
    )
    by_region = {r["region"]: r for r in summary["regions"]}
    assert by_region["110000"]["outflow_wan"] == 1000.0
    assert by_region["110000"]["inflow_wan"] == 300.0
    assert by_region["110000"]["net_wan"] == -700.0
    assert by_region["310000"]["net_wan"] == 700.0
    assert summary["internal_edges"] == 1
    assert summary["total_cross_amount_wan"] == 1300.0


def test_hhi_known_value():
    # 两省各占流出 50%：HHI = 5000²/10000 × 2 = 5000
    summary = region_summary(
        [
            edge("1", "110000", "310000", amount_wan=1000.0),
            edge("2", "310000", "110000", amount_wan=1000.0),
        ]
    )
    assert summary["hhi"] == 5000.0


def test_hhi_none_when_no_amounts():
    summary = region_summary([edge("1", "110000", "310000", amount_wan=None)])
    assert summary["hhi"] is None


def test_timeline_buckets_by_year_and_orders():
    timeline = flow_timeline(
        [
            edge("1", "110000", "310000", amount_wan=100.0, year=2018),
            edge("2", "440000", "110000", amount_wan=50.0, year=2022),
            edge("3", "110000", "440000", amount_wan=70.0, year=2018),
        ]
    )
    assert [(t["year"], t["edge_count"], t["amount_wan"]) for t in timeline] == [
        (2018, 2, 170.0),
        (2022, 1, 50.0),
    ]


def test_industry_flows_excludes_missing_industry():
    result = industry_flows(
        [
            (edge("1", "110000", "310000", amount_wan=500.0, obj="A"), "金融业"),
            (edge("2", "110000", "440000", amount_wan=200.0, obj="B"), None),
        ]
    )
    assert result["missing_industry_edges"] == 1
    assert result["rows"] == [
        {"from_region": "110000", "industry": "金融业", "edge_count": 1, "amount_wan": 500.0}
    ]


def test_determinism_same_input_same_output():
    edges = [
        edge("1", "110000", "310000", amount_wan=100.0),
        edge("2", "440000", "110000", amount_wan=400.0),
        edge("3", "330000", "110000", amount_wan=400.0),
    ]
    assert aggregate_flows(edges) == aggregate_flows(list(reversed(edges)))
