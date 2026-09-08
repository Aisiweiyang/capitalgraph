"""实体解析包：候选生成、特征评分、决策记录与合并执行。

硬规则（提示词 §5 / ADR-009）：名称相似只产生候选；
标识符（USCC 等带命名空间）一致才可由规则自动判定为同一实体。
"""

from cg_entity_resolution.features import PairFeatures, compute_features
from cg_entity_resolution.scoring import ScoringWeights, Thresholds, score_pair
from cg_entity_resolution.service import ResolutionService, apply_merge

__all__ = [
    "PairFeatures",
    "ResolutionService",
    "ScoringWeights",
    "Thresholds",
    "apply_merge",
    "compute_features",
    "score_pair",
]
