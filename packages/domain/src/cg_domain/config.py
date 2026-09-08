"""环境配置。

密钥只允许来自环境变量（提示词 §7）；此处仅定义结构与默认值，
默认值必须是保守且不泄露真实信息的占位。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PenetrationDefaults:
    """穿透算法默认护栏。API 允许在护栏内收紧，不允许放宽超过硬上限。"""

    max_depth: int = 6
    min_ratio: float = 0.0001  # 低于该有效比例的路径剪枝
    max_paths: int = 5000
    max_nodes: int = 20000
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class Settings:
    """跨进程共享的基础配置（API/worker/CLI 通用）。"""

    env: str = "dev"
    database_url: str = "sqlite+aiosqlite:///./data/capitalgraph.sqlite3"
    storage_dir: str = "./data/objects"
    store_raw_documents: bool = True
    connector_rate_limit_per_sec: float = 0.2
    ingest_max_document_bytes: int = 5 * 1024 * 1024
    penetration: PenetrationDefaults = field(default_factory=PenetrationDefaults)
    ubo_min_effective_ratio: float = 0.25

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            env=_env("CG_ENV", "dev"),
            database_url=_env("CG_DATABASE_URL", "sqlite+aiosqlite:///./data/capitalgraph.sqlite3"),
            storage_dir=_env("CG_STORAGE_DIR", "./data/objects"),
            store_raw_documents=_env_bool("CG_STORE_RAW_DOCUMENTS", True),
            connector_rate_limit_per_sec=_env_float("CG_CONNECTOR_RATE_LIMIT_PER_SEC", 0.2),
            ingest_max_document_bytes=_env_int("CG_INGEST_MAX_DOCUMENT_BYTES", 5 * 1024 * 1024),
            penetration=PenetrationDefaults(
                max_depth=_env_int("CG_PENETRATION_MAX_DEPTH", 6),
                min_ratio=_env_float("CG_PENETRATION_MIN_RATIO", 0.0001),
                max_paths=_env_int("CG_PENETRATION_MAX_PATHS", 5000),
                max_nodes=_env_int("CG_PENETRATION_MAX_NODES", 20000),
                timeout_seconds=_env_float("CG_PENETRATION_TIMEOUT_SECONDS", 10.0),
            ),
            ubo_min_effective_ratio=_env_float("CG_UBO_MIN_EFFECTIVE_RATIO", 0.25),
        )


def load_settings() -> Settings:
    return Settings.from_env()
