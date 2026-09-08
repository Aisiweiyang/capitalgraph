"""契约模型测试：比例换算、时态校验、配置规范化。"""

from datetime import date

import pytest

from cg_domain.enums import ControlType, EntityKind, Predicate, RatioUnit
from cg_domain.errors import RatioError, ValidationError
from cg_domain.models import EntityRecord, PenetrationConfig, StatementRecord
from cg_domain.orm import RATIO_SCALE


def test_ratio_percent_to_scaled():
    from cg_domain.models import ratio_to_scaled, scaled_to_percent

    assert ratio_to_scaled(51.0, RatioUnit.PERCENT) == round(0.51 * RATIO_SCALE)
    assert ratio_to_scaled(0.51, RatioUnit.FRACTION) == round(0.51 * RATIO_SCALE)
    assert scaled_to_percent(ratio_to_scaled(33.333333, RatioUnit.PERCENT)) == 33.333333
    assert scaled_to_percent(None) is None


def test_ratio_out_of_range_rejected():
    with pytest.raises(RatioError):
        StatementRecord(
            subject_key="src:x:1",
            predicate=Predicate.HOLDS_SHARES,
            object_key="src:x:2",
            valid_from=date(2020, 1, 1),
            share_ratio=101.0,
        )


def test_statement_temporal_validation():
    with pytest.raises(ValidationError):
        StatementRecord(
            subject_key="src:x:1",
            predicate=Predicate.HOLDS_SHARES,
            object_key="src:x:2",
            valid_from=date(2020, 1, 2),
            valid_to=date(2020, 1, 1),
            share_ratio=10.0,
        )


def test_holds_shares_requires_ratio_and_controls_requires_type():
    with pytest.raises(RatioError):
        StatementRecord(
            subject_key="src:x:1",
            predicate=Predicate.HOLDS_SHARES,
            object_key="src:x:2",
            valid_from=date(2020, 1, 1),
        )
    with pytest.raises(ValidationError):
        StatementRecord(
            subject_key="src:x:1",
            predicate=Predicate.CONTROLS,
            object_key="src:x:2",
            valid_from=date(2020, 1, 1),
        )


def test_entity_record_key_and_norm_name():
    record = EntityRecord(
        connector_id="synthetic",
        external_id="C0001",
        kind=EntityKind.COMPANY,
        name="华康科技（北京）有限公司",
        uscc="91110000ABCDEF0XY",
    )
    assert record.key == "src:synthetic:C0001"
    assert record.norm_name == "华康科技(北京)有限公司"


def test_penetration_config_canonical_json_deterministic():
    a = PenetrationConfig(at=date(2024, 1, 1), direction="up")
    b = PenetrationConfig(direction="up", at=date(2024, 1, 1))
    assert a.canonical_json() == b.canonical_json()
    # 越界配置被拒
    with pytest.raises(ValueError):
        PenetrationConfig(max_depth=99)
