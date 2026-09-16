"""v0.6 性能基线：2000 声明规模下 /evidence/coverage/timeline 与 /evidence/staleness。

- 建库由 tests/performance/conftest.py 的会话级夹具提供（三份性能基线共用）；
- 只记录与断言护栏（超时阈值），实测值写入 TEST_REPORT.md。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.performance

from conftest import bench  # noqa: E402


def test_evidence_quality_endpoints_at_2000_statements(perf_env):
    client = perf_env["client"]
    statements = perf_env["stats"]["statements_created"]
    entities_total = perf_env["stats"]["entities_created"]

    timeline_times = bench(
        lambda: client.get("/api/v1/evidence/coverage/timeline", headers=perf_env["viewer_headers"])
    )
    timeline_resp = client.get(
        "/api/v1/evidence/coverage/timeline", headers=perf_env["viewer_headers"]
    )
    assert timeline_resp.status_code == 200
    covered_years = len(timeline_resp.json()["timeline"])

    stale_times = bench(
        lambda: client.get(
            "/api/v1/evidence/staleness",
            params={"years": 5},
            headers=perf_env["viewer_headers"],
        )
    )
    stale_resp = client.get(
        "/api/v1/evidence/staleness", params={"years": 5}, headers=perf_env["viewer_headers"]
    )
    assert stale_resp.status_code == 200
    stale_count = stale_resp.json()["stale_count"]

    print(
        f"\n[perf-v0.6] 环境: {perf_env['info']}\n"
        f"[perf-v0.6] 规模: entities={entities_total} statements={statements} "
        f"(目标 ≈2000) timeline 年度数={covered_years} 5 年阈值候选={stale_count}\n"
        f"[perf-v0.6] /evidence/coverage/timeline: {timeline_times}\n"
        f"[perf-v0.6] /evidence/staleness: {stale_times}"
    )
    # 护栏：与 v0.5 端点同数量级（默认超时 10s）；实际应远低于此
    assert timeline_times["max_ms"] < 10_000
    assert stale_times["max_ms"] < 10_000
    # 确定性断言：seed=42 下质押证据恒存在（2019-01-01 取证），趋势覆盖 ≥1 个年度
    assert covered_years >= 1
    assert stale_count >= 1
