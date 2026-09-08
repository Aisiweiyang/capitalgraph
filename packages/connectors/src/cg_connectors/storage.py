"""内容寻址对象存储（本地实现，接口对齐 S3 语义）。

键 = sha256 hex；写入原子（临时文件 + rename），防止半写快照。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


class ObjectStore:
    def put(self, content: bytes) -> str:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


def _assert_content_key(key: str) -> None:
    """防路径穿越：只接受 64 位十六进制内容哈希键（T07 威胁缓解）。"""
    if len(key) != 64 or any(ch not in "0123456789abcdef" for ch in key):
        raise ValueError("非法对象键：必须是 sha256 十六进制")


class LocalObjectStore(ObjectStore):
    def __init__(self, root_dir: str | os.PathLike[str]) -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        _assert_content_key(key)
        # 二级分桶避免单目录文件过多
        return self.root / key[:2] / key

    def put(self, content: bytes) -> str:
        key = hashlib.sha256(content).hexdigest()
        path = self._path(key)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                os.replace(tmp_name, path)
            except BaseException:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
                raise
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()
