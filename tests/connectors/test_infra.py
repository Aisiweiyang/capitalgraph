"""对象存储与 connector 基础设施测试。"""

import pytest
from cg_connectors.base import RateLimiter
from cg_connectors.storage import LocalObjectStore
from cg_domain.config import Settings
from cg_domain.models import ConnectorSpec


def test_object_store_roundtrip(tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    content = b"hello capitalgraph"
    key = store.put(content)
    assert len(key) == 64
    assert store.exists(key)
    assert store.get(key) == content
    # 内容寻址：相同内容同键
    assert store.put(content) == key
    store.delete(key)
    assert not store.exists(key)


def test_object_store_rejects_non_content_keys(tmp_path):
    store = LocalObjectStore(tmp_path)
    for bad in ("../escape", "a/b", "A" * 64, "zzz", ""):
        with pytest.raises(ValueError, match="非法对象键"):
            store.get(bad)
        with pytest.raises(ValueError, match="非法对象键"):
            store._path(bad)


def test_rate_limiter_enforces_interval():
    import time

    limiter = RateLimiter(100.0)
    start = time.monotonic()
    for _ in range(5):
        limiter.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 4 / 100.0 - 0.01  # 至少 4 个完整间隔


def test_rate_limiter_zero_rate_is_noop():
    limiter = RateLimiter(0)
    assert limiter.wait() is None


def test_connector_spec_defaults_conservative():
    spec = ConnectorSpec(connector_id="t")
    assert spec.allowed_use == "internal-research"
    assert spec.respects_robots is True
    assert spec.touches_auth_boundary is False
    assert spec.enabled_by_default is False
    assert spec.rate_limit_per_sec <= 1.0


def test_idempotency_key_depends_on_params():
    from cg_connectors.base import ConnectorContext
    from cg_connectors.synthetic import SyntheticConnector

    connector = SyntheticConnector()
    k1 = connector.idempotency_key(ConnectorContext(params={"seed": "1"}))
    k2 = connector.idempotency_key(ConnectorContext(params={"seed": "1"}))
    k3 = connector.idempotency_key(ConnectorContext(params={"seed": "2"}))
    assert k1 == k2
    assert k1 != k3


def test_settings_defaults_are_safe():
    s = Settings()
    assert s.store_raw_documents is True
    assert s.penetration.max_depth <= 12
    assert 0 < s.penetration.timeout_seconds <= 60
