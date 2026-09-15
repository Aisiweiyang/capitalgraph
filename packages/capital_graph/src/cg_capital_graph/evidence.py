"""证据覆盖率统计（纯函数、确定性、无 IO）。

口径（ADR-018）：
- 输入为某时点有效声明（active 且时点有效）与其"是否登记了证据片段"的存在性标记；
- 声明证据覆盖率 = 有证据片段的 active 声明占比；按谓词/连接器/年度分组输出；
- 缺失证据的声明显式列出（样本上限内），只呈现、不修复、不补值；
- 全部分组与样本排序确定，同输入同输出。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

EVIDENCE_COVERAGE_VERSION = "cg-evidence-coverage/1.0.0"

EVIDENCE_COVERAGE_ASSUMPTIONS: tuple[str, ...] = (
    "覆盖率只呈现数据现状，不修复、不推断；缺失证据的声明显式列出（样本有上限）；",
    "无证据声明 ≠ 无效声明：其结论权重由研究者自行判断；",
    "统计结果为研究参考（算法候选），不构成法律认定或投资建议。",
)

MISSING_SAMPLE_LIMIT = 50  # 缺失清单样本上限（全量以 missing_statement_ids 计数为准）


@dataclass(frozen=True)
class EvidenceStatRow:
    """覆盖率统计输入行：时点有效的一条声明 + 是否有证据片段。"""

    statement_id: str
    subject_id: str
    object_id: str
    predicate: str
    connector_id: str
    year: int
    has_evidence: bool


@dataclass(frozen=True)
class CoverageYearRow:
    """覆盖率趋势输入行：单一年度的聚合统计（调用方按 valid_from 年度先行聚合）。"""

    year: int
    total: int
    covered: int


def evidence_coverage(rows: list[EvidenceStatRow]) -> dict:
    """声明证据覆盖率统计：总体 + 按谓词/连接器/年度分组 + 缺失样本清单。"""

    def group_stats(key_of) -> list[dict]:
        buckets: dict[object, list[EvidenceStatRow]] = defaultdict(list)
        for r in rows:
            buckets[key_of(r)].append(r)
        stats = []
        for key in sorted(buckets, key=str):
            group = buckets[key]
            covered = sum(1 for r in group if r.has_evidence)
            total = len(group)
            stats.append(
                {
                    "key": key,
                    "total": total,
                    "covered": covered,
                    "missing": total - covered,
                    "coverage_percent": round(covered * 100.0 / total, 2) if total else None,
                }
            )
        return stats

    total = len(rows)
    covered = sum(1 for r in rows if r.has_evidence)
    missing = sorted(
        (r for r in rows if not r.has_evidence),
        key=lambda r: (r.year, r.predicate, r.statement_id),
    )
    return {
        "algorithm_version": EVIDENCE_COVERAGE_VERSION,
        "total_active_statements": total,
        "covered_statements": covered,
        "missing_statements": total - covered,
        "coverage_percent": round(covered * 100.0 / total, 2) if total else None,
        "by_predicate": group_stats(lambda r: r.predicate),
        "by_connector": group_stats(lambda r: r.connector_id or "unknown"),
        "by_year": group_stats(lambda r: r.year),
        "missing_sample_size": min(len(missing), MISSING_SAMPLE_LIMIT),
        "missing_samples": [
            {
                "statement_id": r.statement_id,
                "subject_id": r.subject_id,
                "object_id": r.object_id,
                "predicate": r.predicate,
                "connector_id": r.connector_id,
                "year": r.year,
            }
            for r in missing[:MISSING_SAMPLE_LIMIT]
        ],
        "assumptions": EVIDENCE_COVERAGE_ASSUMPTIONS,
    }


# --------------------------------------------------------------- 覆盖率趋势（v0.6，ADR-019）

EVIDENCE_TIMELINE_VERSION = "cg-evidence-timeline/1.0.0"

EVIDENCE_TIMELINE_ASSUMPTIONS: tuple[str, ...] = (
    "趋势 = 按声明 valid_from 年度分组的覆盖率逐年对比；首年无前值，delta 为空；",
    "覆盖率只呈现数据现状，不修复、不推断；逐年的变化不构成数据质量改进或恶化的认定；",
    "统计结果为研究参考（算法候选），不构成法律认定或投资建议。",
)


def coverage_timeline(rows: list[CoverageYearRow]) -> list[dict]:
    """覆盖率年度趋势：逐年 {year, total, covered, missing, coverage_percent, delta_vs_prev}。

    口径（ADR-019）：
    - 输出按年度升序；同输入同输出（确定性）；
    - delta_vs_prev = 本年覆盖率 − 上一可比较年度覆盖率（百分数，两位小数）；
      首年（或前序年度覆盖率无定义时）为 None；
    - 同年度重复输入行按计数合并（total/covered 求和），零声明年度覆盖率记 None。
    """
    merged: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # year -> [total, covered]
    for r in rows:
        merged[r.year][0] += r.total
        merged[r.year][1] += r.covered

    timeline: list[dict] = []
    prev_percent: float | None = None
    for year in sorted(merged):
        total, covered = merged[year]
        missing = total - covered
        percent = round(covered * 100.0 / total, 2) if total else None
        delta = (
            round(percent - prev_percent, 2)
            if percent is not None and prev_percent is not None
            else None
        )
        timeline.append(
            {
                "year": year,
                "total": total,
                "covered": covered,
                "missing": missing,
                "coverage_percent": percent,
                "delta_vs_prev": delta,
            }
        )
        if percent is not None:
            prev_percent = percent
    return timeline


# --------------------------------------------------------------- 证据时效规则（v0.6，ADR-020）

STALE_EVIDENCE_VERSION = "cg-evidence-staleness/1.0.0"

STALE_EVIDENCE_ASSUMPTIONS: tuple[str, ...] = (
    "时效规则只提示证据快照取证时间早于阈值窗口的声明（算法候选/研究用途），不构成证据无效，"
    "也不构成信用、法律或投资结论；时效是否影响结论权重由研究者自行判断（参照 ISO/IEC 25012 "
    "对 Currentness 的口径：新度要求取决于使用语境，而非数据本身）；",
    "按声明取证据快照的最近一次取证时间判定（多快照取最大）；无证据声明不进本规则，"
    "由覆盖率缺失通道另行呈现；",
    "快照缺省取证时间为入库时间；捕获时间晚于时点的声明不参与判定。",
)

STALE_YEARS_MIN = 1
STALE_YEARS_MAX = 30
STALE_YEARS_DEFAULT = 5


@dataclass(frozen=True)
class EvidenceFreshnessRow:
    """时效规则输入行：时点有效声明 + 证据快照的最近取证时间（date 粒度）。"""

    statement_id: str
    subject_id: str
    object_id: str
    predicate: str
    last_captured_at: date


def _shift_years(d: date, years: int) -> date:
    """按整年平移；2 月 29 日遇平年落到 2 月 28 日。"""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def stale_evidence(
    rows: list[EvidenceFreshnessRow], *, at: date, years: int = STALE_YEARS_DEFAULT
) -> dict:
    """证据时效候选：max(快照取证时间) < at − years 年 的声明显式列出。

    只呈现、不写库、不认定；阈值 years 可配（1..30，默认 5）；输出全排序，同输入同输出。
    """
    if not STALE_YEARS_MIN <= years <= STALE_YEARS_MAX:
        raise ValueError(f"years 须在 {STALE_YEARS_MIN}..{STALE_YEARS_MAX}，收到 {years}")
    cutoff = _shift_years(at, -years)
    candidates = sorted(
        (r for r in rows if r.last_captured_at < cutoff),
        key=lambda r: (r.last_captured_at, r.predicate, r.statement_id),
    )
    return {
        "algorithm_version": STALE_EVIDENCE_VERSION,
        "at": at.isoformat(),
        "years": years,
        "cutoff": cutoff.isoformat(),
        "stale_count": len(candidates),
        "stale_candidates": [
            {
                "statement_id": r.statement_id,
                "subject_id": r.subject_id,
                "object_id": r.object_id,
                "predicate": r.predicate,
                "last_captured_at": r.last_captured_at.isoformat(),
                "age_years": round((at - r.last_captured_at).days / 365.25, 2),
            }
            for r in candidates
        ],
        "assumptions": STALE_EVIDENCE_ASSUMPTIONS,
    }
