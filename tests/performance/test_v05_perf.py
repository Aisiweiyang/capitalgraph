"""v0.5 性能基线：2000 声明规模下 /events 与 /families/compare 响应时间。

- 数据为确定性合成（seed=42），规模以实际导入统计为准并随报告输出；
- 建库由 tests/performance/conftest.py 的会话级夹具提供（三份性能基线共用）；
- 只记录与断言护栏（超时阈值），不伪造数字；实测值写入 TEST_REPORT.md。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.performance

_WINDOW = {"from": "2020-01-01", "to": "2024-01-01"}

from conftest import bench  # noqa: E402


def test_events_and_families_compare_at_2000_statements(perf_env):
    client = perf_env["client"]
    statements = perf_env["stats"]["statements_created"]
    entities_total = perf_env["stats"]["entities_created"]

    events_times = bench(
        lambda: client.get("/api/v1/events", params=_WINDOW, headers=perf_env["admin_headers"])
    )
    events_resp = client.get("/api/v1/events", params=_WINDOW, headers=perf_env["admin_headers"])
    assert events_resp.status_code == 200
    events_total = events_resp.json()["total"]

    compare_times = bench(
        lambda: client.get(
            "/api/v1/families/compare", params=_WINDOW, headers=perf_env["admin_headers"]
        )
    )
    compare_resp = client.get(
        "/api/v1/families/compare", params=_WINDOW, headers=perf_env["admin_headers"]
    )
    assert compare_resp.status_code == 200
    flows_times = bench(
        lambda: client.get(
            "/api/v1/flows/compare", params=_WINDOW, headers=perf_env["admin_headers"]
        )
    )
    assert (
        client.get(
            "/api/v1/flows/compare", params=_WINDOW, headers=perf_env["admin_headers"]
        ).status_code
        == 200
    )

    print(
        f"\n[perf-v0.5] 环境: {perf_env['info']}\n"
        f"[perf-v0.5] 规模: entities={entities_total} statements={statements} (目标 ≈2000)\n"
        f"[perf-v0.5] /events（窗口 {events_total} 事件）: {events_times}\n"
        f"[perf-v0.5] /families/compare: {compare_times}\n"
        f"[perf-v0.5] /flows/compare: {flows_times}"
    )
    # 护栏：与穿透护栏同数量级（默认超时 10s）；实际应远低于此
    assert events_times["max_ms"] < 10_000
    assert compare_times["max_ms"] < 10_000
    assert flows_times["max_ms"] < 10_000
    # 事件流在合成数据上的确定性窗口内应有事件（2018 基线 + 2022 转移）
    assert events_total >= 2
