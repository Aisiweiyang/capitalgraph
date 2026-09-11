"""CapitalGraph 图计算包。

纯函数实现：输入为边集合与配置，输出为可复现的结构化结果。
不依赖数据库与网络；比例全程使用缩放整数与 Fraction 精确运算，
仅在输出边界按 ROUND_HALF_EVEN 舍入到 1e-8。
"""

from cg_capital_graph.analysis import (
    AnalysisReport,
    CrossHolding,
    PathResult,
    PenetrationResult,
    ShareholderAggregate,
    UBOCandidate,
    aggregate_by_shareholder,
    analyse,
    config_hash,
    cross_holdings,
    detect_cycles,
    result_to_jsonable,
    ubo_candidates,
)
from cg_capital_graph.engine import (
    ALGORITHM_VERSION,
    GraphEdge,
    PenetrationTimeoutError,
    PenetrationTruncatedError,
    build_adjacency,
    penetrate,
)
from cg_capital_graph.flows import (
    FlowEdge,
    RegionFlow,
    aggregate_flows,
    cross_region,
    flow_timeline,
    industry_flows,
    region_summary,
)

__all__ = [
    "ALGORITHM_VERSION",
    "AnalysisReport",
    "CrossHolding",
    "FlowEdge",
    "GraphEdge",
    "PathResult",
    "PenetrationResult",
    "PenetrationTimeoutError",
    "PenetrationTruncatedError",
    "RegionFlow",
    "ShareholderAggregate",
    "UBOCandidate",
    "aggregate_by_shareholder",
    "aggregate_flows",
    "analyse",
    "build_adjacency",
    "config_hash",
    "cross_holdings",
    "cross_region",
    "detect_cycles",
    "flow_timeline",
    "industry_flows",
    "penetrate",
    "region_summary",
    "result_to_jsonable",
    "ubo_candidates",
]
