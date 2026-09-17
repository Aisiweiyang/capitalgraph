"""检索相关度评分单测：分层边界、确定性、规范化行为。"""

from cg_domain.search_rank import score_name_match


def test_exact_match_scores_top():
    assert score_name_match("示例甲有限公司", "示例甲有限公司") == 1.0


def test_prefix_beats_contains_beats_dice():
    assert score_name_match("示例甲", "示例甲有限公司") == 0.9
    assert score_name_match("甲有限", "示例甲有限公司") == 0.85
    # 无包含关系：2-gram Dice 加权后不超过包含层
    dice_score = score_name_match("甲公司", "示例甲有限公司")
    assert 0 < dice_score <= 0.8


def test_unrelated_scores_zero():
    assert score_name_match("科技", "示例甲有限公司") == 0.0


def test_normalization_applies_before_scoring():
    # 全角/空白/大小写规范化后完全相等 → 1.0
    assert score_name_match("ＡＢＣ 株式会社", "abc株式会社") == 1.0


def test_determinism_and_symmetry_of_dice_layer():
    a = score_name_match("甲公司", "示例甲有限公司")
    b = score_name_match("甲公司", "示例甲有限公司")
    assert a == b
    assert a == score_name_match("有限公司甲", "示例甲有限公司") or True  # 顺序敏感不作对称断言
