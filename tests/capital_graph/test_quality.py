"""质量规则族纯函数单测：有效性 / 唯一性 / 跨源一致性（确定性、边界显式）。"""

from __future__ import annotations

from cg_capital_graph import (
    IdentifierRow,
    StatementKeyRow,
    cross_source_conflicts,
    duplicate_statements,
    identifier_validity,
)


def _ident(entity_id: str, value: str, namespace: str = "uscc") -> IdentifierRow:
    return IdentifierRow(entity_id=entity_id, namespace=namespace, value=value)


def _stmt(
    sid: str,
    subject: str = "s1",
    obj: str = "o1",
    predicate: str = "holds_shares_in",
    connector: str = "synthetic",
    ratio: int | None = 30_000_000,
) -> StatementKeyRow:
    return StatementKeyRow(
        statement_id=sid,
        subject_id=subject,
        object_id=obj,
        predicate=predicate,
        connector_id=connector,
        share_ratio_scaled=ratio,
    )


def test_validity_counts_only_uscc_and_lists_invalid():
    # 合法 USCC（GB 32100-2015 校验位正确，由生成器同款算法构造）
    valid = "91350100M000100Y1R"
    rows = [
        _ident("e1", valid),
        _ident("e2", "91110000XXXXXXXXXX"),  # 长度合法、校验位非法
        _ident("e3", "lei-NOT-CHECKED", namespace="lei"),  # 其他命名空间不核查
    ]
    out = identifier_validity(rows)
    assert out["checked"] == 2
    assert out["invalid_count"] == 1
    assert out["invalid"] == [{"entity_id": "e2", "value": "91110000XXXXXXXXXX"}]


def test_validity_sorted_deterministic():
    rows = [_ident("e2", "91110000XXXXXXXXXX"), _ident("e1", "91110000XXXXXXXXXX")]
    out = identifier_validity(rows)
    assert [x["entity_id"] for x in out["invalid"]] == ["e1", "e2"]
    assert identifier_validity(rows) == identifier_validity(list(reversed(rows)))


def test_uniqueness_groups_parallel_active_only():
    rows = [
        _stmt("s3", connector="other"),
        _stmt("s1"),
        _stmt("s2"),
        _stmt("s9", subject="s2", obj="o2"),  # 不同键：单独一组不成立
    ]
    out = duplicate_statements(rows)
    assert out["group_count"] == 1
    assert out["groups"][0]["statement_ids"] == ["s1", "s2", "s3"]


def test_uniqueness_no_duplicates_empty():
    rows = [_stmt("s1"), _stmt("s2", obj="o2")]
    out = duplicate_statements(rows)
    assert out == {"group_count": 0, "groups": []}


def test_consistency_flags_cross_connector_ratio_conflict():
    rows = [
        _stmt("s1", connector="a", ratio=30_000_000),
        _stmt("s2", connector="b", ratio=51_000_000),
    ]
    out = cross_source_conflicts(rows)
    assert out["conflict_count"] == 1
    values = out["conflicts"][0]["values"]
    assert [v["connector_id"] for v in values] == ["a", "b"]
    assert {v["share_ratio"] for v in values} == {30.0, 51.0}


def test_consistency_agreement_and_missing_ratio_not_conflicts():
    same_value = [
        _stmt("s1", connector="a", ratio=30_000_000),
        _stmt("s2", connector="b", ratio=30_000_000),  # 多源印证：不是冲突
    ]
    assert cross_source_conflicts(same_value)["conflict_count"] == 0

    missing = [
        _stmt("s1", connector="a", ratio=None),
        _stmt("s2", connector="b", ratio=51_000_000),  # 任一侧缺失：不可比，跳过
    ]
    assert cross_source_conflicts(missing)["conflict_count"] == 0

    same_connector = [
        _stmt("s1", connector="a", ratio=30_000_000),
        _stmt("s2", connector="a", ratio=51_000_000),  # 同连接器内部差异：不进本规则
    ]
    assert cross_source_conflicts(same_connector)["conflict_count"] == 0


def test_determinism_and_robust_to_input_order():
    rows = [
        _stmt("s1", connector="a", ratio=30_000_000),
        _stmt("s2", connector="b", ratio=51_000_000),
        _stmt("s3", connector="b"),
    ]
    assert cross_source_conflicts(rows) == cross_source_conflicts(list(reversed(rows)))
    assert duplicate_statements(rows) == duplicate_statements(list(reversed(rows)))
