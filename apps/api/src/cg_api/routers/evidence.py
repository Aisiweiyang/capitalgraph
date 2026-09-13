"""证据工作台路由：覆盖率统计、来源文档导航、声明反查证据（viewer 可读，只读）。

口径沿 ADR-018：覆盖率 = 有证据片段的 active 声明占比（时点有效），
缺失证据的声明只呈现、不修复；deep-link 以 statement_id 为证据引用键。
"""

from __future__ import annotations

from datetime import date

from cg_capital_graph import EvidenceStatRow, evidence_coverage
from fastapi import APIRouter, HTTPException, Query

from cg_api.auth import ViewerUser
from cg_api.deps import Repo

router = APIRouter(prefix="/evidence", tags=["证据工作台"])

_LOOKUP_LIMIT = 200


@router.get("/coverage")
async def evidence_coverage_stats(
    _user: ViewerUser,
    repo: Repo,
    at: date | None = None,
):
    """声明证据覆盖率：总体 + 按谓词/连接器/年度分组 + 缺失样本清单（只呈现，不修复）。"""
    rows = await repo.evidence_coverage_rows(at)
    stats = evidence_coverage(
        [
            EvidenceStatRow(
                statement_id=r.statement_id,
                subject_id=r.subject_id,
                object_id=r.object_id,
                predicate=r.predicate,
                connector_id=r.connector_id,
                year=r.year,
                has_evidence=r.has_evidence,
            )
            for r in rows
        ]
    )
    stats["at"] = at.isoformat() if at else None
    return stats


@router.get("/documents")
async def evidence_documents(_user: ViewerUser, repo: Repo):
    """来源文档 → 快照 → 片段 导航树（证据工作台浏览视图）。"""
    documents = await repo.evidence_documents()
    fragment_total = sum(s["fragment_count"] for d in documents for s in d["snapshots"])
    return {
        "count": len(documents),
        "fragment_total": fragment_total,
        "documents": documents,
    }


@router.get("/lookup")
async def evidence_lookup(
    _user: ViewerUser,
    repo: Repo,
    ids: str = Query(min_length=1, max_length=20000, description="逗号分隔的声明 ID"),
):
    """按声明 ID 批量反查证据片段（deep-link 与报告证据表的数据源）。"""
    wanted = [x.strip() for x in ids.split(",") if x.strip()]
    if not wanted:
        raise HTTPException(422, "ids 不能为空")
    if len(wanted) > _LOOKUP_LIMIT:
        raise HTTPException(422, f"单次最多查询 {_LOOKUP_LIMIT} 条声明")
    evidence = await repo.evidence_for_statements(wanted)
    return {
        "requested": len(wanted),
        "found": len(evidence),
        "missing_statement_ids": [sid for sid in wanted if sid not in evidence],
        "evidence": evidence,
    }
