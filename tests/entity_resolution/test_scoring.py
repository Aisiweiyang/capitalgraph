"""score_pair 单测：分支覆盖与阈值边界（不依赖数据库，纯函数确定性）。"""

from __future__ import annotations

from cg_entity_resolution.features import PairFeatures
from cg_entity_resolution.scoring import (
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    Thresholds,
    score_pair,
)


def _features(**overrides) -> PairFeatures:
    base = {
        "left_id": "a",
        "right_id": "b",
        "same_uscc": False,
        "same_lei": False,
        "same_source_key": False,
        "norm_name_equal": False,
        "short_name_equal": False,
        "name_similarity": 0.0,
        "kind_match": False,
    }
    base.update(overrides)
    return PairFeatures(**base)


def test_single_identifier_lands_in_review_band():
    """单一标识符 0.60 分：够复核带（0.45）但不够 merge（0.90），不因有一致标识符而直判。"""
    out = score_pair(_features(same_uscc=True))
    assert out.score == DEFAULT_WEIGHTS.same_uscc
    assert out.suggested == "review"
    assert out.reasons == ["统一社会信用代码一致"]


def test_identifier_plus_corroboration_at_boundary_merges():
    """0.60 + 0.30×1.0 = 0.90，恰好达到 auto_merge：有标识符证据即可判 merge。"""
    out = score_pair(_features(same_uscc=True, name_similarity=1.0))
    assert out.score == DEFAULT_THRESHOLDS.auto_merge
    assert out.suggested == "merge"


def test_short_name_branch_used_only_when_norm_name_differs():
    out = score_pair(_features(short_name_equal=True))
    assert out.score == DEFAULT_WEIGHTS.short_name_equal
    assert "剥离后缀后名称一致" in out.reasons
    assert "规范化名称完全一致" not in out.reasons

    out2 = score_pair(_features(norm_name_equal=True, short_name_equal=True))
    assert out2.score == DEFAULT_WEIGHTS.norm_name_equal
    assert "规范化名称完全一致" in out2.reasons
    assert "剥离后缀后名称一致" not in out2.reasons, "完全一致时应互斥，不再叠加短名分支"


def test_name_similarity_adds_weighted_share_above_threshold():
    # 0.84：不进相似度分支
    below = score_pair(_features(name_similarity=0.84))
    assert below.score == 0.0
    # 0.85：权重 × 相似度入分
    at = score_pair(_features(name_similarity=0.85))
    assert at.score == round(DEFAULT_WEIGHTS.name_similarity * 0.85, 6)
    assert "名称相似度 0.85" in at.reasons


def test_high_score_without_identifier_stays_review():
    """名称完全一致 + 类型一致 + 高相似度仍缺标识符证据：只能进复核带，不得 merge。"""
    out = score_pair(_features(norm_name_equal=True, kind_match=True, name_similarity=1.0))
    assert out.score == 1.0, "权重和超过 1.0 时截断到 1.0"
    assert out.suggested == "review", "满分但无标识符证据：仍然只进复核，不得 merge"


def test_all_signals_cap_score_at_one():
    out = score_pair(
        _features(
            same_uscc=True,
            same_lei=True,
            same_source_key=True,
            norm_name_equal=True,
            name_similarity=1.0,
            kind_match=True,
        )
    )
    assert out.score == 1.0
    assert out.suggested == "merge"
    assert len(out.reasons) == 5, "kind_match 只加权不计原因行（与实现口径一致）"


def test_custom_thresholds_boundaries():
    weights = DEFAULT_WEIGHTS
    th = Thresholds(auto_merge=0.90, review_band=0.45, reject_below=0.35)
    # 恰好等于阈值：≥ 语义（含边界，不靠浮点巧合——用整定权值控制分数）
    custom_w = type(weights)(same_uscc=0.90)
    out = score_pair(_features(same_uscc=True), weights=custom_w, thresholds=th)
    assert out.score == 0.90
    assert out.suggested == "merge"

    review_th = Thresholds(auto_merge=0.95, review_band=0.90, reject_below=0.35)
    out2 = score_pair(_features(same_uscc=True), weights=custom_w, thresholds=review_th)
    assert out2.suggested == "review", "低于 auto_merge 但不低于 review_band 时应进复核"


def test_determinism_same_input_same_output():
    f = _features(same_source_key=True, short_name_equal=True, kind_match=True)
    assert score_pair(f) == score_pair(f)
