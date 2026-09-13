"""证据覆盖率统计纯函数单测（切片 C）。

口径（ADR-018）：覆盖率 = 有证据片段的 active 声明占比；分组与缺失样本全排序；
缺失只呈现不修复；同输入同输出。
"""

from __future__ import annotations

from cg_capital_graph import EvidenceStatRow, evidence_coverage


def row(
    sid: str,
    predicate: str = "holds_shares",
    connector: str = "synthetic",
    year: int = 2020,
    has_ev: bool = True,
    subject: str = "S",
    obj: str = "O",
):
    return EvidenceStatRow(
        statement_id=sid,
        subject_id=subject,
        object_id=obj,
        predicate=predicate,
        connector_id=connector,
        year=year,
        has_evidence=has_ev,
    )


def test_full_coverage():
    rows = [row("1"), row("2", predicate="controls"), row("3", year=2021)]
    out = evidence_coverage(rows)
    assert out["total_active_statements"] == 3
    assert out["covered_statements"] == 3
    assert out["missing_statements"] == 0
    assert out["coverage_percent"] == 100.0
    assert out["missing_samples"] == []


def test_coverage_with_missing_and_groupings():
    rows = [
        row("1", predicate="holds_shares", connector="synthetic", year=2020, has_ev=True),
        row("2", predicate="holds_shares", connector="synthetic", year=2020, has_ev=False),
        row("3", predicate="controls", connector="csv", year=2021, has_ev=False),
        row("4", predicate="provides_guarantee", connector="synthetic", year=2021, has_ev=True),
    ]
    out = evidence_coverage(rows)
    assert out["coverage_percent"] == 50.0
    by_pred = {g["key"]: g for g in out["by_predicate"]}
    assert by_pred["holds_shares"] == {
        "key": "holds_shares",
        "total": 2,
        "covered": 1,
        "missing": 1,
        "coverage_percent": 50.0,
    }
    by_conn = {g["key"]: g for g in out["by_connector"]}
    assert by_conn["csv"]["missing"] == 1
    assert by_conn["synthetic"]["coverage_percent"] == 66.67
    by_year = {g["key"]: g for g in out["by_year"]}
    assert by_year[2020]["total"] == 2
    assert by_year[2021]["covered"] == 1


def test_missing_samples_sorted_and_capped():
    rows = [row(f"m{i:02d}", year=2020 + i % 2, has_ev=False) for i in range(60)]
    rows += [row("ok", has_ev=True)]
    out = evidence_coverage(rows)
    assert out["missing_statements"] == 60
    assert out["missing_sample_size"] == 50
    assert len(out["missing_samples"]) == 50
    keys = [(s["year"], s["predicate"], s["statement_id"]) for s in out["missing_samples"]]
    assert keys == sorted(keys)


def test_deterministic_and_empty():
    assert evidence_coverage([])["coverage_percent"] is None
    rows = [row("1", has_ev=False), row("2", has_ev=True)]
    assert evidence_coverage(rows) == evidence_coverage(list(reversed(rows)))
