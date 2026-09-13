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
