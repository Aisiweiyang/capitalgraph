"""检索相关度评分（纯函数、确定性、无 IO）。

口径（ADR-003 补记）：
- 评分分层：规范化完全相等 1.0 > 前缀 0.9 > 包含 0.85 > 2-gram Dice × 0.8（≤0.8）；
- 企业名称短，2-gram（相邻双字符）比逐字交集更能保留相邻性语义；
- 命中集合仍由 SQL 包含匹配决定，本评分只决定**展示顺序**——
  0 分不会出现在包含匹配的结果里（含查询串才有 Dice 意义），分层保底 0.85 起步。
"""

from __future__ import annotations

from cg_domain.normalization import normalize_name

_TOP_EXACT = 1.0
_TOP_PREFIX = 0.9
_TOP_CONTAINS = 0.85
_DICE_WEIGHT = 0.8


def _bigrams(text: str) -> set[str]:
    return {text[i : i + 2] for i in range(len(text) - 1)}


def score_name_match(query: str, name: str) -> float:
    """查询串与实体主档名称的相关度评分（0..1，规范化后比较）。"""
    q = normalize_name(query)
    n = normalize_name(name)
    if not q or not n:
        return 0.0
    if q == n:
        return _TOP_EXACT
    if n.startswith(q):
        return _TOP_PREFIX
    if q in n:
        return _TOP_CONTAINS
    if len(q) < 2 or len(n) < 2:
        return 0.0
    q_grams = _bigrams(q)
    n_grams = _bigrams(n)
    dice = 2 * len(q_grams & n_grams) / (len(q_grams) + len(n_grams))
    return round(dice * _DICE_WEIGHT, 6)
