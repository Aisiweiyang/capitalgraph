"""v0.7 性能基线：2000 声明规模下 /evidence/quality 质量总览端点。

- 建库由 tests/performance/conftest.py 的会话级夹具提供（三份性能基线共用）；
- /evidence/quality 内部为四次只读扫描（覆盖率 / 时效 / 声明键 / 标识符），
  护栏放宽到两倍（20s），实测值写入 TEST_REPORT.md。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.performance

from conftest import bench  # noqa: E402


def test_quality_overview_at_2000_statements(perf_env):
    client = perf_env["client"]

    quality_times = bench(
        lambda: client.get(
            "/api/v1/evidence/quality", params={"years": 5}, headers=perf_env["viewer_headers"]
        )
    )
    resp = client.get(
        "/api/v1/evidence/quality", params={"years": 5}, headers=perf_env["viewer_headers"]
    )
    assert resp.status_code == 200
    body = resp.json()

    # RBAC 护栏：只读端点对 viewer 开放，匿名拒绝
    assert client.get("/api/v1/evidence/quality").status_code == 401

    print(
        f"\n[perf-v0.7] 环境: {perf_env['info']}\n"
        f"[perf-v0.7] /evidence/quality（五维度总览）: {quality_times}\n"
        f"[perf-v0.7] counts: {body['counts']}"
    )
    # 护栏：内部四次扫描，放宽到两倍护栏仍远低于默认超时
    assert quality_times["max_ms"] < 20_000
    # 确定性：合成库已知候选（质押时效 2019-01-01）
    assert body["counts"]["staleness"] >= 1
