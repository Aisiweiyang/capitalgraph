"""变更事件流纯函数单测（切片 A，先于实现编写）。

口径依据（ADR-017）：事件 = from/to 两个时点有效声明快照的集合差异，
只陈述"声明层面的变化"，不做动机推断；比例仅比较两侧齐备的缩放整数，
任一侧缺失显式标注不比较数值；同输入同输出（事件全排序）。
"""

from __future__ import annotations

from cg_capital_graph import EventStatement, diff_events, events_for_entity

R60 = 60 * 10**6  # 60%（RATIO_SCALE = 1e8，缩放整数）
R50 = 50 * 10**6
R40 = 40 * 10**6


def stmt(
    sid: str,
    subject: str,
    obj: str,
    predicate: str = "holds_shares",
    ratio: int | None = None,
) -> EventStatement:
    return EventStatement(
        statement_id=sid,
        subject_id=subject,
        object_id=obj,
        predicate=predicate,
        share_ratio_scaled=ratio,
    )


# ---------------------------------------------------------------- 基础性质


def test_identical_snapshots_produce_zero_events():
    snap = [
        stmt("1", "P0", "C0", ratio=R60),
        stmt("2", "P1", "C1", predicate="controls"),
        stmt("3", "C0", "C1", predicate="provides_guarantee"),
    ]
    result = diff_events(snap, list(snap))
    assert result.events == ()
    assert result.counts_by_type == ()
    assert result.from_statement_count == 3
    assert result.to_statement_count == 3


def test_deterministic_and_sorted_output():
    old = [stmt("2", "PB", "C2", ratio=R40), stmt("1", "PA", "C1", ratio=R60)]
    new = [stmt("3", "PA", "C1", ratio=R50), stmt("4", "PB", "C2", ratio=R40)]
    a = diff_events(old, new)
    b = diff_events(list(reversed(old)), list(reversed(new)))
    assert a == b
    keys = [(e.event_type, e.subject_id, e.object_id) for e in a.events]
    assert keys == sorted(keys)


def test_counts_by_type():
    old = [
        stmt("1", "P0", "C0", ratio=R60),
        stmt("2", "P0", "C1", ratio=R50),
        stmt("3", "P1", "C2", predicate="controls"),
    ]
    new = [
        stmt("4", "P0", "C0", ratio=R40),
        stmt("5", "P9", "C9", predicate="provides_guarantee"),
    ]
    result = diff_events(old, new)
    counts = dict(result.counts_by_type)
    assert counts == {
        "control_lost": 1,
        "guarantee_added": 1,
        "holding_ratio_changed": 1,
        "holding_removed": 1,
    }


# ---------------------------------------------------------------- 事件类型正确性


def test_holding_added_and_removed_types():
    old = [stmt("1", "P0", "C0", ratio=R60)]
    new = [stmt("2", "P1", "C0", ratio=R60)]
    events = {e.event_type: e for e in diff_events(old, new).events}
    assert set(events) == {"holding_added", "holding_removed"}
    assert events["holding_added"].statement_ids == ("2",)
    assert events["holding_added"].subject_id == "P1"
    # 单声明的新增/失效附该侧比例（仅展示，不与另一侧比较）
    assert events["holding_added"].after_percent == 60.0
    assert events["holding_added"].ratio_comparable is False
    assert events["holding_added"].delta_percent is None
    assert events["holding_removed"].statement_ids == ("1",)
    assert events["holding_removed"].subject_id == "P0"
    assert events["holding_removed"].before_percent == 60.0


def test_ratio_change_carries_before_after_delta():
    old = [stmt("1", "P0", "C0", ratio=R60)]
    new = [stmt("2", "P0", "C0", ratio=50 * 10**6)]
    events = diff_events(old, new).events
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "holding_ratio_changed"
    assert ev.before_percent == 60.0
    assert ev.after_percent == 50.0
    assert ev.delta_percent == -10.0
    assert ev.ratio_comparable is True
    assert ev.statement_ids == ("2",)
    assert ev.prior_statement_ids == ("1",)
    assert ev.evidence_keys == ("1", "2")


def test_ratio_unchanged_across_supersede_produces_no_event():
    # 同键重录（supersede）且比例不变：事实未变，不产生事件
    old = [stmt("1", "P0", "C0", ratio=R60)]
    new = [stmt("2", "P0", "C0", ratio=R60)]
    assert diff_events(old, new).events == ()


def test_missing_ratio_explicit_not_compared():
    # 旧声明缺比例：显式标注 comparable=False，绝不比较/补值
    old = [stmt("1", "P0", "C0", ratio=None)]
    new = [stmt("2", "P0", "C0", ratio=R40)]
    events = diff_events(old, new).events
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "holding_ratio_changed"
    assert ev.before_percent is None
    assert ev.after_percent == 40.0
    assert ev.delta_percent is None
    assert ev.ratio_comparable is False


def test_control_gained_and_lost():
    old = [stmt("1", "P0", "C0", predicate="controls")]
    new = [stmt("2", "P1", "C0", predicate="controls")]
    events = {e.event_type: e for e in diff_events(old, new).events}
    assert set(events) == {"control_gained", "control_lost"}
    assert events["control_gained"].subject_id == "P1"
    assert events["control_lost"].statement_ids == ("1",)


def test_guarantee_added_and_released():
    old = [stmt("1", "C0", "C1", predicate="provides_guarantee")]
    assert [e.event_type for e in diff_events(old, []).events] == ["guarantee_released"]
    new = [stmt("2", "C0", "C1", predicate="provides_guarantee")]
    assert [e.event_type for e in diff_events([], new).events] == ["guarantee_added"]


def test_pledge_added_and_released():
    old = [stmt("1", "C0", "C1", predicate="pledges_shares", ratio=R40)]
    assert [e.event_type for e in diff_events(old, []).events] == ["pledge_released"]
    new = [stmt("2", "C0", "C1", predicate="pledges_shares", ratio=R40)]
    assert [e.event_type for e in diff_events([], new).events] == ["pledge_added"]


def test_generic_predicates_use_statement_added_removed():
    old = [stmt("1", "P0", "C0", predicate="invests_in")]
    new = [stmt("2", "P0", "C0", predicate="invests_in")]
    types = [e.event_type for e in diff_events(old, new).events]
    assert types == ["statement_added", "statement_removed"]


def test_key_replacement_with_different_ratio_is_single_ratio_event():
    # 同键、声明更换（supersede 链）且比例变化 → 只产生一条比例事件，不重复计增删
    old = [stmt("1", "P0", "C0", ratio=R60)]
    new = [stmt("2", "P0", "C0", ratio=R50)]
    events = diff_events(old, new).events
    assert [e.event_type for e in events] == ["holding_ratio_changed"]


def test_partial_overlap_falls_back_to_add_remove_events():
    # 同键多条声明部分重叠：比例合计无法无歧义归因 → 退化为按声明增删事件；
    # 单条新增/失效声明附"该条声明自身"的比例（声明层面事实）
    old = [stmt("1", "P0", "C0", ratio=R60), stmt("2", "P0", "C0", ratio=R40)]
    new = [stmt("1", "P0", "C0", ratio=R60), stmt("3", "P0", "C0", ratio=R40)]
    by_type = {e.event_type: e for e in diff_events(old, new).events}
    assert set(by_type) == {"holding_added", "holding_removed"}
    assert by_type["holding_removed"].statement_ids == ("2",)
    assert by_type["holding_removed"].before_percent == 40.0
    assert by_type["holding_added"].statement_ids == ("3",)
    assert by_type["holding_added"].after_percent == 40.0


def test_empty_inputs():
    assert diff_events([], []).events == ()


# ---------------------------------------------------------------- 实体过滤


def test_events_for_entity_filters_both_directions():
    old = [stmt("1", "P0", "C0", ratio=R60)]
    new = [stmt("2", "P1", "C0", ratio=R60)]
    events = diff_events(old, new).events
    by_c0 = events_for_entity(events, "C0")
    assert len(by_c0) == 2
    by_p0 = events_for_entity(events, "P0")
    assert [e.event_type for e in by_p0] == ["holding_removed"]
    assert events_for_entity(events, "P9") == ()
