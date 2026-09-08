"""评分与阈值。权重与阈值集中定义并随候选记录留档（可追溯、可复现）。"""

from __future__ import annotations

from dataclasses import dataclass

from cg_entity_resolution.features import PairFeatures

METHOD = "cg-resolution/weighted-v1"
METHOD_VERSION = "1.0.0"


@dataclass(frozen=True)
class ScoringWeights:
    same_uscc: float = 0.60
    same_lei: float = 0.55
    same_source_key: float = 0.45
    norm_name_equal: float = 0.25
    short_name_equal: float = 0.15
    name_similarity: float = 0.30  # 乘以相似度值
    kind_match: float = 0.05


@dataclass(frozen=True)
class Thresholds:
    """score ≥ auto_merge：标识符级一致，规则可直接判 merge；
    review_band：高相似但无标识符证据，必须人工复核；
    reject_below：低于此值不生成候选。
    """

    auto_merge: float = 0.90
    review_band: float = 0.65
    reject_below: float = 0.50


DEFAULT_WEIGHTS = ScoringWeights()
DEFAULT_THRESHOLDS = Thresholds()


@dataclass(frozen=True)
class ScoredPair:
    score: float
    suggested: str  # merge / review / none
    reasons: list[str]


def score_pair(
    features: PairFeatures,
    *,
    weights: ScoringWeights = DEFAULT_WEIGHTS,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> ScoredPair:
    score = 0.0
    reasons: list[str] = []
    if features.same_uscc:
        score += weights.same_uscc
        reasons.append("统一社会信用代码一致")
    if features.same_lei:
        score += weights.same_lei
        reasons.append("LEI 一致")
    if features.same_source_key:
        score += weights.same_source_key
        reasons.append("来源内部键一致")
    if features.norm_name_equal:
        score += weights.norm_name_equal
        reasons.append("规范化名称完全一致")
    elif features.short_name_equal:
        score += weights.short_name_equal
        reasons.append("剥离后缀后名称一致")
    if features.name_similarity >= 0.85:
        score += weights.name_similarity * features.name_similarity
        reasons.append(f"名称相似度 {features.name_similarity:.2f}")
    if features.kind_match:
        score += weights.kind_match

    score = min(1.0, round(score, 6))
    if score >= thresholds.auto_merge and (
        features.same_uscc or features.same_lei or features.same_source_key
    ):
        suggested = "merge"
    elif score >= thresholds.review_band:
        suggested = "review"
    else:
        suggested = "none"
    return ScoredPair(score=score, suggested=suggested, reasons=reasons)
