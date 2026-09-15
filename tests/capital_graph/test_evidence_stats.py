"""证据覆盖率统计纯函数单测（切片 C）。

口径（ADR-018）：覆盖率 = 有证据片段的 active 声明占比；分组与缺失样本全排序；
缺失只呈现不修复；同输入同输出。
v0.6 切片 A：coverage_timeline 覆盖率趋势（ADR-019 口径）。
"""

from __future__ import annotations

from cg_capital_graph import (
    EVIDENCE_TIMELINE_VERSION,
    CoverageYearRow,
    EvidenceStatRow,
    coverage_timeline,
    evidence_coverage,
)


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


# ------------------------------------------------ v0.6 切片 A：覆盖率趋势（ADR-019）


def yrow(year: int, total: int, covered: int) -> CoverageYearRow:
    return CoverageYearRow(year=year, total=total, covered=covered)


def test_timeline_grouping_shape_and_delta():
    out = coverage_timeline(
        [
            yrow(2020, 4, 3),
            yrow(2021, 2, 1),
            yrow(2022, 5, 5),
        ]
    )
    assert [r["year"] for r in out] == [2020, 2021, 2022]
    assert out[0] == {
        "year": 2020,
        "total": 4,
        "covered": 3,
        "missing": 1,
        "coverage_percent": 75.0,
        "delta_vs_prev": None,  # 首年无前值
    }
    assert out[1]["delta_vs_prev"] == round(50.0 - 75.0, 2)  # -25.0
    assert out[1]["missing"] == 1
    assert out[2]["coverage_percent"] == 100.0
    assert out[2]["delta_vs_prev"] == 50.0
    # 版本与口径由 API 层附带；行键固定
    assert all(
        {"year", "total", "covered", "missing", "coverage_percent", "delta_vs_prev"} == set(r)
        for r in out
    )


def test_timeline_empty_and_zero_total_year():
    assert coverage_timeline([]) == []
    # 零声明年度：覆盖率无定义（None），其后年度的 delta 对照最近一个可定义覆盖率
    out = coverage_timeline([yrow(2020, 0, 0), yrow(2021, 4, 2)])
    assert out[0]["coverage_percent"] is None
    assert out[0]["delta_vs_prev"] is None
    assert out[1]["coverage_percent"] == 50.0
    assert out[1]["delta_vs_prev"] is None
    # 全零年度同理
    assert coverage_timeline([yrow(2019, 0, 0)])[0]["delta_vs_prev"] is None


def test_timeline_unsorted_input_and_duplicate_years():
    # 输入未排序也输出升序；同年度重复行按计数合并（total/covered 求和）
    out = coverage_timeline([yrow(2021, 2, 1), yrow(2020, 2, 2), yrow(2021, 2, 1)])
    assert [r["year"] for r in out] == [2020, 2021]
    assert out[0]["delta_vs_prev"] is None
    assert out[1] == {
        "year": 2021,
        "total": 4,
        "covered": 2,
        "missing": 2,
        "coverage_percent": 50.0,
        "delta_vs_prev": -50.0,
    }


def test_timeline_deterministic():
    rows = [yrow(2020, 3, 1), yrow(2021, 7, 4), yrow(2022, 2, 2)]
    assert coverage_timeline(rows) == coverage_timeline(list(reversed(rows)))
    assert coverage_timeline(rows) == coverage_timeline(list(rows))


def test_timeline_rounding_two_decimals():
    out = coverage_timeline([yrow(2020, 3, 1), yrow(2021, 3, 2)])
    assert out[0]["coverage_percent"] == 33.33
    assert out[1]["delta_vs_prev"] == 33.34  # 66.67 - 33.33


def test_timeline_algorithm_version_registered():
    assert EVIDENCE_TIMELINE_VERSION.startswith("cg-evidence-timeline/")
