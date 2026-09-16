"""变更事件流：两个时点有效声明快照的集合对比（纯函数、确定性、无 IO）。

口径（ADR-017）：
- 输入为 from/to 两个时点的有效声明（仓储按 status=active 且时点有效过滤），
  本层只做集合对比，不访问数据库、不做动机推断——事件只陈述"声明层面的变化"；
- 事件键 = (subject_id, predicate, object_id)。键出现 → 新增类事件（含新股东进入）；
  键消失 → 失效类事件（superseded/到期/退出在有效快照层面等价：旧事实不再有效）；
- 键在两侧均存在时，仅当"单声明对单声明且比例可比较"时产生 holding_ratio_changed
  （带前后值与差值）；任一侧比例缺失显式标注 comparable=False，绝不比较缺失值、
  绝不补值；同键重录且比例不变 → 无事件（事实未变）；多条声明的键部分重叠时
  退化为按声明增删事件（比例无法无歧义归因）；
- controls/guarantee/pledge 的出现与消失有专用事件类型（控制权获得/丧失、担保
  新增/解除、质押新增/解除），其余谓词用通用 statement_added/statement_removed；
- 新增/失效事件附该侧单声明的持股比例（after/before_percent；多条声明时无法无歧义
  归因则为 None），仅作展示、不与另一侧比较（comparable=False，无差值）；
- 事件按 (event_type, subject_id, object_id) 排序，同输入同输出。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

EVENTS_ALGORITHM_VERSION = "cg-events/1.0.0"

EVENTS_ASSUMPTIONS: tuple[str, ...] = (
    "事件由 from/to 两个时点的有效声明快照对比派生，只陈述声明层面的变化，不做动机推断；",
    "声明失效 = 该（主体,谓词,对象）键在 to 时点不再有效；superseded/到期/退出在快照层面等价；",
    "比例增减仅比较两侧齐备的缩放整数值，任一侧缺失时显式标注且不比较数值；",
    "事件为研究参考口径（算法候选），不构成法律认定或投资建议。",
)

_RATION_SCALE = 10**8

_ADDED_EVENT_TYPES = {
    "holds_shares": "holding_added",
    "controls": "control_gained",
    "provides_guarantee": "guarantee_added",
    "pledges_shares": "pledge_added",
}
_REMOVED_EVENT_TYPES = {
    "holds_shares": "holding_removed",
    "controls": "control_lost",
    "provides_guarantee": "guarantee_released",
    "pledges_shares": "pledge_released",
}


@dataclass(frozen=True)
class EventStatement:
    """事件对比输入行：某时点有效的一条声明。时点过滤由仓储完成。"""

    statement_id: str
    subject_id: str
    object_id: str
    predicate: str
    share_ratio_scaled: int | None = None


@dataclass(frozen=True)
class ChangeEvent:
    """一条声明层面的变更事件。statement_ids 为 to 侧（或消失侧）声明，即证据引用键。"""

    event_type: str
    subject_id: str
    object_id: str
    predicate: str
    statement_ids: tuple[str, ...]
    prior_statement_ids: tuple[str, ...] = ()  # from 侧声明（比例事件的前值来源）
    before_percent: float | None = None
    after_percent: float | None = None
    delta_percent: float | None = None
    ratio_comparable: bool = False

    @property
    def evidence_keys(self) -> tuple[str, ...]:
        """证据引用键：以声明 ID 反查证据链（去重、保持先后顺序）。"""
        return tuple(dict.fromkeys((*self.prior_statement_ids, *self.statement_ids)))


@dataclass(frozen=True)
class EventsResult:
    """事件流对比总输出。events 按 (event_type, subject_id, object_id) 排序。"""

    events: tuple[ChangeEvent, ...]
    counts_by_type: tuple[tuple[str, int], ...]
    from_statement_count: int
    to_statement_count: int
    algorithm_version: str = EVENTS_ALGORITHM_VERSION
    assumptions: tuple[str, ...] = EVENTS_ASSUMPTIONS


def _percent(scaled: int | None) -> float | None:
    if scaled is None:
        return None
    return round(scaled * 100.0 / _RATION_SCALE, 6)


def _single_ratio(rows: Sequence[EventStatement]) -> float | None:
    """单声明组的比例（百分数）；多条声明时无法无歧义归因，返回 None。"""
    if len(rows) != 1:
        return None
    return _percent(rows[0].share_ratio_scaled)


def _added_type(predicate: str) -> str:
    return _ADDED_EVENT_TYPES.get(predicate, "statement_added")


def _removed_type(predicate: str) -> str:
    return _REMOVED_EVENT_TYPES.get(predicate, "statement_removed")


def diff_events(
    from_statements: list[EventStatement],
    to_statements: list[EventStatement],
) -> EventsResult:
    """对比两个时点的有效声明集合，产出确定性事件流。"""
    from_map: dict[tuple[str, str, str], list[EventStatement]] = {}
    to_map: dict[tuple[str, str, str], list[EventStatement]] = {}
    for row in from_statements:
        from_map.setdefault((row.subject_id, row.predicate, row.object_id), []).append(row)
    for row in to_statements:
        to_map.setdefault((row.subject_id, row.predicate, row.object_id), []).append(row)
    for bucket in (*from_map.values(), *to_map.values()):
        bucket.sort(key=lambda r: r.statement_id)

    events: list[ChangeEvent] = []
    for key in sorted(set(from_map) | set(to_map)):
        subject, predicate, obj = key
        old = from_map.get(key, ())
        new = to_map.get(key, ())
        old_ids = {r.statement_id for r in old}
        new_ids = {r.statement_id for r in new}

        if not old:
            events.append(
                ChangeEvent(
                    event_type=_added_type(predicate),
                    subject_id=subject,
                    object_id=obj,
                    predicate=predicate,
                    statement_ids=tuple(r.statement_id for r in new),
                    after_percent=_single_ratio(new),
                )
            )
            continue
        if not new:
            events.append(
                ChangeEvent(
                    event_type=_removed_type(predicate),
                    subject_id=subject,
                    object_id=obj,
                    predicate=predicate,
                    statement_ids=tuple(r.statement_id for r in old),
                    before_percent=_single_ratio(old),
                )
            )
            continue

        if old_ids == new_ids:
            continue  # 同一批声明，载荷相同（声明不可变）→ 事实未变

        if (
            predicate == "holds_shares"
            and len(old) == 1
            and len(new) == 1
            and (old[0].share_ratio_scaled is not None or new[0].share_ratio_scaled is not None)
        ):
            before, after = old[0].share_ratio_scaled, new[0].share_ratio_scaled
            if before == after:
                continue  # 重录且比例不变 → 事实未变
            comparable = before is not None and after is not None
            before_percent, after_percent = _percent(before), _percent(after)
            delta_percent = (
                round(after_percent - before_percent, 6)
                if comparable and before_percent is not None and after_percent is not None
                else None
            )
            events.append(
                ChangeEvent(
                    event_type="holding_ratio_changed",
                    subject_id=subject,
                    object_id=obj,
                    predicate=predicate,
                    statement_ids=(new[0].statement_id,),
                    prior_statement_ids=(old[0].statement_id,),
                    before_percent=before_percent,
                    after_percent=after_percent,
                    delta_percent=delta_percent,
                    ratio_comparable=comparable,
                )
            )
            continue

        # 部分重叠或比例不可归因：退化为按声明的增删事件；
        # 单条新增/失效声明附"该条声明自身"的比例（声明层面事实，无归因歧义）
        removed_rows = [r for r in old if r.statement_id in old_ids - new_ids]
        added_rows = [r for r in new if r.statement_id in new_ids - old_ids]
        if removed_rows:
            events.append(
                ChangeEvent(
                    event_type=_removed_type(predicate),
                    subject_id=subject,
                    object_id=obj,
                    predicate=predicate,
                    statement_ids=tuple(r.statement_id for r in removed_rows),
                    before_percent=_single_ratio(removed_rows),
                )
            )
        if added_rows:
            events.append(
                ChangeEvent(
                    event_type=_added_type(predicate),
                    subject_id=subject,
                    object_id=obj,
                    predicate=predicate,
                    statement_ids=tuple(r.statement_id for r in added_rows),
                    after_percent=_single_ratio(added_rows),
                )
            )

    events.sort(key=lambda e: (e.event_type, e.subject_id, e.object_id))
    counts: dict[str, int] = {}
    for e in events:
        counts[e.event_type] = counts.get(e.event_type, 0) + 1
    return EventsResult(
        events=tuple(events),
        counts_by_type=tuple(sorted(counts.items())),
        from_statement_count=len(from_statements),
        to_statement_count=len(to_statements),
    )


def events_for_entity(
    events: tuple[ChangeEvent, ...] | list[ChangeEvent], entity_id: str
) -> tuple[ChangeEvent, ...]:
    """按实体过滤事件（主体或对象任一端命中）。"""
    return tuple(e for e in events if entity_id in (e.subject_id, e.object_id))
