"""变更事件流路由：全局异动流与实体维度过滤（只读派生视图，viewer 可读）。

口径沿 ADR-017：事件由 from/to 两个时点的有效声明快照对比派生（cg-events 纯函数），
返回附口径说明与输入时点；只读、不写库、不做动机推断，结果为研究参考。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from cg_capital_graph import (
    ChangeEvent,
    EventsResult,
    EventStatement,
    diff_events,
)
from cg_domain.orm import Entity
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from cg_api.auth import ViewerUser
from cg_api.deps import Repo

router = APIRouter(prefix="/events", tags=["变更事件"])

DEFAULT_WINDOW_DAYS = 730  # 未显式给出 from 时，默认回看两年

EVENT_TYPE_LABELS: dict[str, str] = {
    "holding_added": "持股新增",
    "holding_removed": "持股失效",
    "holding_ratio_changed": "持股比例增减",
    "control_gained": "控制权获得",
    "control_lost": "控制权丧失",
    "guarantee_added": "担保新增",
    "guarantee_released": "担保解除",
    "pledge_added": "质押新增",
    "pledge_released": "质押解除",
    "statement_added": "声明新增",
    "statement_removed": "声明失效",
}


def resolve_window(from_: date | None, to: date | None) -> tuple[date, date]:
    to_date = to or date.today()
    from_date = from_ or (to_date - timedelta(days=DEFAULT_WINDOW_DAYS))
    if from_date > to_date:
        raise HTTPException(422, "参数校验失败：from 不得晚于 to")
    return from_date, to_date


async def load_events(
    repo: Repo, from_: date | None, to: date | None
) -> tuple[EventsResult, date, date]:
    """加载两个时点的有效声明快照并做事件对比（切片 A 口径的唯一入口）。"""
    from_date, to_date = resolve_window(from_, to)
    from_rows = await repo.event_rows(from_date)
    to_rows = await repo.event_rows(to_date)
    result = diff_events(
        [
            EventStatement(
                statement_id=r.statement_id,
                subject_id=r.subject_id,
                object_id=r.object_id,
                predicate=r.predicate,
                share_ratio_scaled=r.share_ratio_scaled,
            )
            for r in from_rows
        ],
        [
            EventStatement(
                statement_id=r.statement_id,
                subject_id=r.subject_id,
                object_id=r.object_id,
                predicate=r.predicate,
                share_ratio_scaled=r.share_ratio_scaled,
            )
            for r in to_rows
        ],
    )
    return result, from_date, to_date


async def entity_names(repo: Repo, entity_ids: set[str]) -> dict[str, str]:
    if not entity_ids:
        return {}
    rows = await repo.session.execute(
        select(Entity.id, Entity.primary_name).where(Entity.id.in_(entity_ids))
    )
    return dict(rows.all())


def event_out(ev: ChangeEvent, names: dict[str, str]) -> dict:
    return {
        "event_type": ev.event_type,
        "event_type_label": EVENT_TYPE_LABELS.get(ev.event_type, ev.event_type),
        "subject_id": ev.subject_id,
        "subject_name": names.get(ev.subject_id, ev.subject_id),
        "object_id": ev.object_id,
        "object_name": names.get(ev.object_id, ev.object_id),
        "predicate": ev.predicate,
        "statement_ids": list(ev.statement_ids),
        "prior_statement_ids": list(ev.prior_statement_ids),
        "evidence_keys": list(ev.evidence_keys),
        "before_percent": ev.before_percent,
        "after_percent": ev.after_percent,
        "delta_percent": ev.delta_percent,
        "ratio_comparable": ev.ratio_comparable,
    }


@router.get("")
async def global_events(
    _user: ViewerUser,
    repo: Repo,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    event_type: str | None = Query(default=None, description="按事件类型筛选"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """全局变更事件流（异动页）。分页作用于确定性排序后的事件序列。"""
    result, from_date, to_date = await load_events(repo, from_, to)
    events = list(result.events)
    if event_type:
        events = [e for e in events if e.event_type == event_type]
    names = await entity_names(repo, {e.subject_id for e in events} | {e.object_id for e in events})
    page = events[offset : offset + limit]
    return {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "algorithm_version": result.algorithm_version,
        "total": len(events),
        "returned": len(page),
        "offset": offset,
        "counts_by_type": [
            {"event_type": t, "label": EVENT_TYPE_LABELS.get(t, t), "count": n}
            for t, n in result.counts_by_type
        ],
        "assumptions": list(result.assumptions),
        "events": [event_out(e, names) for e in page],
    }


@router.get("/types")
async def event_types(_user: ViewerUser):
    """事件类型清单（供前端筛选下拉），含中文标签。"""
    return [{"event_type": t, "label": label} for t, label in sorted(EVENT_TYPE_LABELS.items())]
