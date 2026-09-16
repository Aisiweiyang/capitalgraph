"""LocalObjectStore 补充语义：内容寻址去重、删除、缺键报错、原子写失败不落半文件。

基础 roundtrip 与非法键拒绝在 test_infra.py；此处覆盖异常分支。
"""

from __future__ import annotations

import hashlib

import pytest
from cg_connectors.storage import LocalObjectStore


def test_put_is_content_addressed_and_deduplicated(tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    key1 = store.put(b"same-bytes")
    key2 = store.put(b"same-bytes")
    assert key1 == key2 == hashlib.sha256(b"same-bytes").hexdigest()
    # 去重：分桶目录里只应有一个对象文件（.tmp 已被 rename 消费）
    bucket = tmp_path / "objects" / key1[:2]
    assert [p.name for p in bucket.iterdir() if not p.name.endswith(".tmp")] == [key1]


def test_get_missing_key_raises(tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    key = hashlib.sha256(b"never-written").hexdigest()
    with pytest.raises(FileNotFoundError):
        store.get(key)


def test_delete_removes_and_exists_reflects(tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    key = store.put(b"to-delete")
    assert store.exists(key)
    store.delete(key)
    assert not store.exists(key)
    # 删除不存在的键是幂等 no-op
    store.delete(key)


def test_put_failure_leaves_no_temp_file(tmp_path, monkeypatch):
    """写入中途失败：临时文件被清理、目标不出现、异常上抛（原子性）。"""
    import os

    store = LocalObjectStore(tmp_path / "objects")
    real_replace = os.replace

    def boom(*args, **kwargs):
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        store.put(b"doomed-bytes")
    monkeypatch.setattr(os, "replace", real_replace)

    bucket = tmp_path / "objects" / hashlib.sha256(b"doomed-bytes").hexdigest()[:2]
    assert list(bucket.iterdir()) == [], "失败后不得残留临时文件或半写对象"
