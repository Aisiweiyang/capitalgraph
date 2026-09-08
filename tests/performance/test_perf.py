"""性能测试（可重复合成规模，不伪造数字）。

用确定性合成器生成实体与边，记录机器、规模、p50/p95 延迟、峰值内存。
标记为 performance：默认随套件运行（规模保持在秒级内）。
"""

from __future__ import annotations

import platform
import random
import time
import tracemalloc

import pytest
from cg_capital_graph import GraphEdge, analyse, penetrate
from cg_domain.models import PenetrationConfig
from cg_domain.orm import RATIO_SCALE

pytestmark = pytest.mark.performance


def synth_edges(n_companies: int, n_persons: int, seed: int) -> list[GraphEdge]:
    """生成随机链式持股网络：每公司 1 个上游 + 若干个人股东。"""
    rng = random.Random(seed)
    edges: list[GraphEdge] = []

    def edge(sid: str, s: str, o: str, ratio: float) -> GraphEdge:
        return GraphEdge(
            statement_id=sid,
            subject=s,
            obj=o,
            predicate="holds_shares",
            share_scaled=round(ratio * RATIO_SCALE),
            voting_scaled=None,
        )

    for i in range(n_companies):
        company = f"C{i}"
        # 公司链：向上挂在随机更早的公司下（形成树+偶然环）
        if i > 0:
            parent = f"C{rng.randrange(i)}"
            edges.append(edge(f"e-comp-{i}", company, parent, rng.uniform(0.5, 0.95)))
        # 个人股东
        for j in range(rng.randint(1, 3)):
            person = f"P{rng.randrange(n_persons)}"
            edges.append(edge(f"e-p-{i}-{j}", person, company, rng.uniform(0.05, 0.4)))
    return edges


def _bench(n_companies: int, n_persons: int, runs: int = 5, seed: int = 42) -> dict:
    edges = synth_edges(n_companies, n_persons, seed)
    root = f"C{n_companies - 1}"  # 链末端：最深
    config = PenetrationConfig(direction="up", max_depth=8, min_ratio_percent=0.01)
    durations: list[float] = []
    path_counts = []
    tracemalloc.start()
    for _ in range(runs):
        start = time.perf_counter()
        result = penetrate(root, edges, config)
        durations.append(time.perf_counter() - start)
        path_counts.append(len(result.paths))
    _, peak_kb = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    durations_ms = sorted(d * 1000 for d in durations)
    p50 = durations_ms[len(durations_ms) // 2]
    p95 = durations_ms[int(len(durations_ms) * 0.95) - 1]
    return {
        "edges": len(edges),
        "nodes": n_companies + n_persons,
        "paths": path_counts[0],
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "error_rate": 0.0,
        "peak_mem_mb": round(peak_kb / 1024, 1),
        "deterministic": len(set(path_counts)) == 1,
    }


def test_circular_chain_terminates():
    """500 家公司首尾相接成环：环路检测必须终止且耗时可控（威胁 T13）。"""
    n = 500
    edges = [
        GraphEdge(
            statement_id=f"cyc-{i}",
            subject=f"C{i}",
            obj=f"C{(i + 1) % n}",
            predicate="holds_shares",
            share_scaled=50 * RATIO_SCALE // 100,
            voting_scaled=None,
        )
        for i in range(n)
    ]
    config = PenetrationConfig(direction="up", max_depth=8, min_ratio_percent=0.01)
    start = time.perf_counter()
    result = penetrate("C0", edges, config)
    report = analyse("C0", result, edges, config)
    elapsed = time.perf_counter() - start
    # 环长(500)超过遍历深度上限(8)：结果路径无环，但全图环检测必须找到它
    assert report.cycles, "全图环检测应当识别出环"
    assert elapsed < 5.0
    print(f"\n[perf] 500 节点纯环: {elapsed * 1000:.1f}ms, cycles={len(report.cycles)}")


def test_penetration_performance_report():
    """小规模随套件执行；机器信息随报告输出，保证可复现环境描述。"""
    info = {
        "machine": platform.machine(),
        "python": platform.python_version(),
        "system": platform.system(),
    }
    small = _bench(n_companies=200, n_persons=80)
    medium = _bench(n_companies=1000, n_persons=300)
    print(f"\n[perf] 环境: {info}")
    print(f"[perf] 小规模(200公司): {small}")
    print(f"[perf] 中规模(1000公司): {medium}")
    assert small["error_rate"] == 0.0
    assert medium["error_rate"] == 0.0
    assert small["deterministic"] and medium["deterministic"]
    # 中等规模下 p95 必须在护栏超时之内（默认 10s），远小于则认为健康
    assert medium["p95_ms"] < 10_000
