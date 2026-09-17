"""证据工作台路由：覆盖率统计、覆盖率趋势、来源文档导航、声明反查、时效风险（只读为主）。

口径沿 ADR-018/019/020：覆盖率 = 有证据片段的 active 声明占比（时点有效），
趋势按 valid_from 年度分组逐年对比；时效规则只提示算法候选、不构成认定；
缺失证据的声明只呈现、不修复；deep-link 以 statement_id 为证据引用键。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from cg_capital_graph import (
    EVIDENCE_TIMELINE_ASSUMPTIONS,
    EVIDENCE_TIMELINE_VERSION,
    QUALITY_ASSUMPTIONS,
    QUALITY_VERSION,
    STALE_EVIDENCE_VERSION,
    CoverageYearRow,
    EvidenceFreshnessRow,
    EvidenceStatRow,
    IdentifierRow,
    StatementKeyRow,
    coverage_timeline,
    cross_source_conflicts,
    duplicate_statements,
    evidence_coverage,
    identifier_validity,
    ratio_sum_conflicts,
    stale_evidence,
)
from fastapi import APIRouter, HTTPException, Query

from cg_api.auth import AnalystUser, ViewerUser
from cg_api.deps import Ctx, Repo

router = APIRouter(prefix="/evidence", tags=["证据工作台"])

_LOOKUP_LIMIT = 200


@router.get("/coverage")
async def evidence_coverage_stats(
    _user: ViewerUser,
    repo: Repo,
    at: date | None = None,
):
    """声明证据覆盖率：总体 + 按谓词/连接器/年度分组 + 缺失样本清单（只呈现，不修复）。

    附带 timeline（ADR-019 年度趋势行）：与统计共用同一次声明扫描，证据工作台
    一次请求即可同时渲染覆盖率与趋势；独立端点 /coverage/timeline 保留。
    """
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
    by_year: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # year -> [total, covered]
    for r in rows:
        by_year[r.year][0] += 1
        if r.has_evidence:
            by_year[r.year][1] += 1
    stats["timeline"] = coverage_timeline(
        [CoverageYearRow(year=y, total=t, covered=c) for y, (t, c) in by_year.items()]
    )
    return stats


@router.get("/coverage/timeline")
async def evidence_coverage_timeline(
    _user: ViewerUser,
    repo: Repo,
    at: date | None = None,
):
    """覆盖率年度趋势（ADR-019）：复用 /coverage 时点过滤，按 valid_from 年度分组逐年对比。"""
    rows = await repo.evidence_coverage_rows(at)
    by_year: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # year -> [total, covered]
    for r in rows:
        by_year[r.year][0] += 1
        if r.has_evidence:
            by_year[r.year][1] += 1
    timeline = coverage_timeline(
        [CoverageYearRow(year=y, total=t, covered=c) for y, (t, c) in by_year.items()]
    )
    return {
        "at": at.isoformat() if at else None,
        "algorithm_version": EVIDENCE_TIMELINE_VERSION,
        "timeline": timeline,
        "assumptions": EVIDENCE_TIMELINE_ASSUMPTIONS,
    }


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


@router.get("/quality")
async def evidence_quality_overview(
    _user: ViewerUser,
    repo: Repo,
    at: date | None = None,
    years: int = Query(5, ge=1, le=30),
):
    """质量总览（ADR-021）：覆盖率缺失 / 时效 / 有效性 / 唯一性 / 跨源一致性。

    只呈现、不认定；各规则口径独立（见 assumptions）。时效维度与 /staleness 共用 years。
    """
    at_date = at or date.today()

    stale = stale_evidence(
        [
            EvidenceFreshnessRow(
                statement_id=r.statement_id,
                subject_id=r.subject_id,
                object_id=r.object_id,
                predicate=r.predicate,
                last_captured_at=r.last_captured_at,
            )
            for r in await repo.evidence_staleness_rows(at_date)
        ],
        at=at_date,
        years=years,
    )
    coverage = evidence_coverage(
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
            for r in await repo.evidence_coverage_rows(at_date)
        ]
    )
    key_rows = [
        StatementKeyRow(
            statement_id=r.statement_id,
            subject_id=r.subject_id,
            object_id=r.object_id,
            predicate=r.predicate,
            connector_id=r.connector_id,
            share_ratio_scaled=r.share_ratio_scaled,
        )
        for r in await repo.quality_statement_rows(at_date)
    ]
    validity = identifier_validity(
        [
            IdentifierRow(entity_id=r.entity_id, namespace=r.namespace, value=r.value)
            for r in await repo.identifier_rows()
        ]
    )
    uniqueness = duplicate_statements(key_rows)
    consistency = cross_source_conflicts(key_rows)
    ratio_sum = ratio_sum_conflicts(key_rows)

    counts = {
        "coverage_missing": coverage["missing_statements"],
        "staleness": stale["stale_count"],
        "validity": validity["invalid_count"],
        "uniqueness": uniqueness["group_count"],
        "consistency": consistency["conflict_count"],
        "ratio_sum": ratio_sum["conflict_count"],
    }
    return {
        "at": at_date.isoformat(),
        "years": years,
        "algorithm_version": QUALITY_VERSION,
        "assumptions": QUALITY_ASSUMPTIONS,
        "counts": counts,
        "total_candidates": sum(counts.values()),
        "validity": validity,
        "uniqueness": uniqueness,
        "consistency": consistency,
        "ratio_sum": ratio_sum,
    }


@router.post("/quality/scan")
async def evidence_quality_scan(
    user: AnalystUser,
    repo: Repo,
    ctx: Ctx,
    at: date | None = None,
):
    """把有效性/唯一性/跨源一致性候选幂等登记进复核通道（ADR-021 统一登记端点）。

    rule_name 按维度取值（identifier_validity/duplicate_statement/cross_source_conflict）；
    实体级按 entity_id 幂等，声明级按组代表声明幂等；二扫只跳过。写审计。
    """
    at_date = at or date.today()
    key_rows = [
        StatementKeyRow(
            statement_id=r.statement_id,
            subject_id=r.subject_id,
            object_id=r.object_id,
            predicate=r.predicate,
            connector_id=r.connector_id,
            share_ratio_scaled=r.share_ratio_scaled,
        )
        for r in await repo.quality_statement_rows(at_date)
    ]
    validity = identifier_validity(
        [
            IdentifierRow(entity_id=r.entity_id, namespace=r.namespace, value=r.value)
            for r in await repo.identifier_rows()
        ]
    )
    uniqueness = duplicate_statements(key_rows)
    consistency = cross_source_conflicts(key_rows)
    ratio_sum = ratio_sum_conflicts(key_rows)

    created = skipped = 0
    by_rule = {
        "identifier_validity": 0,
        "duplicate_statement": 0,
        "cross_source_conflict": 0,
        "ratio_sum_conflict": 0,
    }

    for item in validity["invalid"]:
        if await repo.has_quality_issue_for_entity("identifier_validity", item["entity_id"]):
            skipped += 1
            continue
        await repo.add_quality_issue(
            "identifier_validity",
            entity_id=item["entity_id"],
            detail={
                "at": at_date.isoformat(),
                "value": item["value"],
                "algorithm_version": QUALITY_VERSION,
            },
        )
        by_rule["identifier_validity"] += 1
        created += 1

    for group in uniqueness["groups"]:
        rep = min(group["statement_ids"])
        if await repo.has_quality_issue("duplicate_statement", rep):
            skipped += 1
            continue
        await repo.add_quality_issue(
            "duplicate_statement",
            entity_id=group["subject_id"],
            statement_id=rep,
            detail={
                "at": at_date.isoformat(),
                "subject_id": group["subject_id"],
                "object_id": group["object_id"],
                "predicate": group["predicate"],
                "statement_ids": group["statement_ids"],
                "algorithm_version": QUALITY_VERSION,
            },
        )
        by_rule["duplicate_statement"] += 1
        created += 1

    for group in ratio_sum["conflicts"]:
        rep = min(group["statement_ids"])
        if await repo.has_quality_issue("ratio_sum_conflict", rep):
            skipped += 1
            continue
        await repo.add_quality_issue(
            "ratio_sum_conflict",
            entity_id=group["object_id"],
            statement_id=rep,
            detail={
                "at": at_date.isoformat(),
                "object_id": group["object_id"],
                "total_percent": group["total_percent"],
                "statement_ids": group["statement_ids"],
                "algorithm_version": QUALITY_VERSION,
            },
        )
        by_rule["ratio_sum_conflict"] += 1
        created += 1

    for conflict in consistency["conflicts"]:
        rep = min(v["statement_id"] for v in conflict["values"])
        if await repo.has_quality_issue("cross_source_conflict", rep):
            skipped += 1
            continue
        await repo.add_quality_issue(
            "cross_source_conflict",
            entity_id=conflict["subject_id"],
            statement_id=rep,
            detail={
                "at": at_date.isoformat(),
                "subject_id": conflict["subject_id"],
                "object_id": conflict["object_id"],
                "predicate": conflict["predicate"],
                "values": conflict["values"],
                "algorithm_version": QUALITY_VERSION,
            },
        )
        by_rule["cross_source_conflict"] += 1
        created += 1

    total_candidates = (
        len(validity["invalid"])
        + len(uniqueness["groups"])
        + len(consistency["conflicts"])
        + len(ratio_sum["conflicts"])
    )
    await repo.audit(
        actor=user["username"],
        action="evidence.quality_scan",
        request_id=ctx.request_id,
        result="ok",
        detail={
            "at": at_date.isoformat(),
            "candidates": total_candidates,
            "created": created,
            "skipped": skipped,
        },
    )
    return {
        "at": at_date.isoformat(),
        "total_candidates": total_candidates,
        "created": created,
        "skipped": skipped,
        "by_rule": by_rule,
        "rule_names": [
            "identifier_validity",
            "duplicate_statement",
            "cross_source_conflict",
            "ratio_sum_conflict",
        ],
    }


@router.get("/staleness")
async def evidence_staleness(
    _user: ViewerUser,
    repo: Repo,
    at: date | None = None,
    years: int = Query(5, ge=1, le=30),
):
    """证据时效候选（ADR-020，只呈现）：快照最近取证早于时点 − years 年的声明显式列出。"""
    at_date = at or date.today()
    rows = await repo.evidence_staleness_rows(at_date)
    return stale_evidence(
        [
            EvidenceFreshnessRow(
                statement_id=r.statement_id,
                subject_id=r.subject_id,
                object_id=r.object_id,
                predicate=r.predicate,
                last_captured_at=r.last_captured_at,
            )
            for r in rows
        ],
        at=at_date,
        years=years,
    )


@router.post("/staleness/scan")
async def evidence_staleness_scan(
    user: AnalystUser,
    repo: Repo,
    ctx: Ctx,
    at: date | None = None,
    years: int = Query(5, ge=1, le=30),
):
    """把时效候选幂等登记进复核通道（QualityIssue，rule_name=stale_source），写审计。

    与 missing_ratio 同通道；同 (rule_name, statement_id) 的 open 标记去重，二扫只跳过。
    """
    at_date = at or date.today()
    rows = await repo.evidence_staleness_rows(at_date)
    report = stale_evidence(
        [
            EvidenceFreshnessRow(
                statement_id=r.statement_id,
                subject_id=r.subject_id,
                object_id=r.object_id,
                predicate=r.predicate,
                last_captured_at=r.last_captured_at,
            )
            for r in rows
        ],
        at=at_date,
        years=years,
    )
    created = skipped = 0
    for cand in report["stale_candidates"]:
        if await repo.has_quality_issue("stale_source", cand["statement_id"]):
            skipped += 1
            continue
        await repo.add_quality_issue(
            "stale_source",
            severity="warning",
            entity_id=cand["subject_id"],
            statement_id=cand["statement_id"],
            detail={
                "at": at_date.isoformat(),
                "years": years,
                "predicate": cand["predicate"],
                "last_captured_at": cand["last_captured_at"],
                "algorithm_version": STALE_EVIDENCE_VERSION,
            },
        )
        created += 1
    await repo.audit(
        actor=user["username"],
        action="evidence.staleness_scan",
        request_id=ctx.request_id,
        result="ok",
        detail={
            "at": at_date.isoformat(),
            "years": years,
            "candidates": report["stale_count"],
            "created": created,
            "skipped": skipped,
        },
    )
    return {
        "at": at_date.isoformat(),
        "years": years,
        "total_candidates": report["stale_count"],
        "created": created,
        "skipped": skipped,
        "rule_name": "stale_source",
    }
