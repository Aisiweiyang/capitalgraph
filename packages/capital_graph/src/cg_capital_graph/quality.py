"""数据质量规则族（纯函数、确定性、无 IO）。

口径（ADR-021，沿 ADR-020 的"只提示、不认定"纪律）：
- 三条规则各自独立：有效性（标识符格式）、唯一性（疑似重复录入）、跨源一致性
  （多连接器取值冲突）；规则间互不隐含，候选互不排除；
- 只呈现现状，不修复、不认定错误；是否采信由研究者自行判断；
- 全部输出排序确定，同输入同输出。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from cg_domain.models import scaled_to_percent
from cg_domain.normalization import is_valid_uscc

QUALITY_VERSION = "cg-evidence-quality/1.0.0"

QUALITY_ASSUMPTIONS: tuple[str, ...] = (
    "三条规则（有效性/唯一性/跨源一致性）只提示数据现状（算法候选/研究用途），"
    "不构成数据错误的认定，也不构成信用、法律或投资结论；是否采信由研究者自行判断；",
    "有效性规则只核查 uscc 命名空间标识符（GB 32100-2015 校验位）；lei 等其他命名空间"
    "的格式规范未纳入，缺数不等于合规；",
    "唯一性规则按时点有效声明分组，已被取代（superseded）的正常历史不进本规则；"
    "同键多声明也可能来自合法的事实细分，分组结果需人工甄别；",
    "跨源一致性规则只比较双方比例均给出的情形；任一侧缺失即显式不可比，绝不补值；"
    "同一连接器内部的取值差异不进本规则。",
)


# --------------------------------------------------------------- 有效性：标识符格式


@dataclass(frozen=True)
class IdentifierRow:
    entity_id: str
    namespace: str
    value: str


def identifier_validity(rows: list[IdentifierRow]) -> dict:
    """uscc 命名空间标识符的 GB 32100-2015 校验位核查；非法者显式列出。

    其他命名空间不核查（计入 checked 之外），避免用不完整的格式规范制造误报。
    输出按 (value, entity_id) 全排序。
    """
    checked = 0
    invalid: list[dict] = []
    for r in rows:
        if r.namespace != "uscc":
            continue
        checked += 1
        if not is_valid_uscc(r.value):
            invalid.append({"entity_id": r.entity_id, "value": r.value})
    invalid.sort(key=lambda x: (x["value"], x["entity_id"]))
    return {"checked": checked, "invalid_count": len(invalid), "invalid": invalid}


# --------------------------------------------------------------- 唯一性：疑似重复录入


@dataclass(frozen=True)
class StatementKeyRow:
    statement_id: str
    subject_id: str
    object_id: str
    predicate: str
    connector_id: str
    share_ratio_scaled: int | None


def duplicate_statements(rows: list[StatementKeyRow]) -> dict:
    """同键 (subject, predicate, object) 的并行 active 声明 > 1 → 疑似重复录入组。

    输入应为某时点的有效声明（status=active 且时点有效），superseded 历史由调用方过滤。
    组内按 statement_id 排序；组间按键全排序。
    """
    grouped: dict[tuple[str, str, str], list[StatementKeyRow]] = defaultdict(list)
    for r in rows:
        grouped[(r.subject_id, r.predicate, r.object_id)].append(r)
    groups = [
        {
            "subject_id": key[0],
            "predicate": key[1],
            "object_id": key[2],
            "statement_ids": sorted(r.statement_id for r in members),
        }
        for key, members in grouped.items()
        if len(members) > 1
    ]
    groups.sort(key=lambda g: (g["subject_id"], g["predicate"], g["object_id"]))
    return {"group_count": len(groups), "groups": groups}


# --------------------------------------------------------------- 跨源一致性：取值冲突


def cross_source_conflicts(rows: list[StatementKeyRow]) -> dict:
    """同键声明来自多个连接器且 share_ratio 均给出但不一致 → 冲突候选。

    口径：任一侧比例缺失即不可比，跳过（不补值）；同连接器内部的差异不进本规则；
    比例一致的多源声明不是冲突（是多源印证）。冲突组内按 (connector_id, statement_id) 排序。
    """
    grouped: dict[tuple[str, str, str], list[StatementKeyRow]] = defaultdict(list)
    for r in rows:
        grouped[(r.subject_id, r.predicate, r.object_id)].append(r)
    conflicts: list[dict] = []
    for key, members in grouped.items():
        comparable = [m for m in members if m.share_ratio_scaled is not None]
        connectors = {m.connector_id for m in comparable}
        if len(connectors) < 2:
            continue
        ratios = {m.share_ratio_scaled for m in comparable}
        if len(ratios) <= 1:
            continue
        conflicts.append(
            {
                "subject_id": key[0],
                "predicate": key[1],
                "object_id": key[2],
                "values": sorted(
                    (
                        {
                            "connector_id": m.connector_id,
                            "share_ratio": scaled_to_percent(m.share_ratio_scaled),
                            "statement_id": m.statement_id,
                        }
                        for m in comparable
                    ),
                    key=lambda v: (v["connector_id"], v["statement_id"]),
                ),
            }
        )
    conflicts.sort(key=lambda c: (c["subject_id"], c["predicate"], c["object_id"]))
    return {"conflict_count": len(conflicts), "conflicts": conflicts}
