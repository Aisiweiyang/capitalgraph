"""证据时效规则纯函数单测（v0.6 切片 B，ADR-020）。

规则：max(快照取证时间) < at − N 年 → 候选陈旧；恰好等于 N 年不算陈旧；
无证据声明不进本规则（缺失证据另有覆盖率/missing_ratio 口径）；同输入同输出。
"""

from __future__ import annotations

from datetime import date

import pytest
from cg_capital_graph import (
    STALE_EVIDENCE_VERSION,
    EvidenceFreshnessRow,
    stale_evidence,
)


def frow(
    sid: str,
    captured: date,
    predicate: str = "holds_shares",
    subject: str = "S",
    obj: str = "O",
) -> EvidenceFreshnessRow:
    return EvidenceFreshnessRow(
        statement_id=sid,
        subject_id=subject,
        object_id=obj,
        predicate=predicate,
        last_captured_at=captured,
    )


def test_boundary_exactly_n_years_not_stale():
    at = date(2024, 6, 15)
    out = stale_evidence(
        [frow("a", date(2019, 6, 15)), frow("b", date(2019, 6, 14))], at=at, years=5
    )
    # cutoff = 2019-06-15：恰好满 5 年的 a 不算候选，早一天的 b 算
    assert out["cutoff"] == "2019-06-15"
    assert [c["statement_id"] for c in out["stale_candidates"]] == ["b"]


def test_years_bounds_validated():
    for bad in (0, 31, -1):
        with pytest.raises(ValueError):
            stale_evidence([], at=date(2024, 1, 1), years=bad)
    assert stale_evidence([], at=date(2024, 1, 1), years=1)["stale_count"] == 0
    assert stale_evidence([], at=date(2024, 1, 1), years=30)["stale_count"] == 0


def test_candidates_sorted_and_complete():
    rows = [
        frow("b", date(2010, 1, 1), predicate="pledges_shares"),
        frow("a", date(2011, 1, 1)),
        frow("c", date(2023, 1, 1)),  # 未过期，不进候选
    ]
    out = stale_evidence(rows, at=date(2024, 1, 1), years=5)
    assert out["stale_count"] == 2
    keys = [
        (c["last_captured_at"], c["predicate"], c["statement_id"]) for c in out["stale_candidates"]
    ]
    assert keys == sorted(keys)
    assert "c" not in {c["statement_id"] for c in out["stale_candidates"]}
    cand = out["stale_candidates"][0]
    assert {
        "statement_id",
        "subject_id",
        "object_id",
        "predicate",
        "last_captured_at",
        "age_years",
    } == set(cand)


def test_shape_and_empty():
    out = stale_evidence([], at=date(2024, 1, 1), years=5)
    assert out["stale_count"] == 0
    assert out["stale_candidates"] == []
    assert out["algorithm_version"] == STALE_EVIDENCE_VERSION
    assert out["algorithm_version"].startswith("cg-evidence-staleness/")
    assert out["at"] == "2024-01-01"
    assert out["years"] == 5
    assert out["assumptions"]


def test_feb_29_cutoff_falls_back_to_feb_28():
    at = date(2024, 2, 29)
    assert stale_evidence([frow("a", date(2019, 2, 28))], at=at, years=5)["cutoff"] == "2019-02-28"
    assert stale_evidence([frow("a", date(2019, 2, 28))], at=at, years=5)["stale_count"] == 0
    assert stale_evidence([frow("a", date(2019, 2, 27))], at=at, years=5)["stale_count"] == 1


def test_deterministic():
    rows = [frow("b", date(2010, 1, 1)), frow("a", date(2011, 6, 1), predicate="controls")]
    assert stale_evidence(rows, at=date(2024, 1, 1)) == stale_evidence(
        list(reversed(rows)), at=date(2024, 1, 1)
    )
