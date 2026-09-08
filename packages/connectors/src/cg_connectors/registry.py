"""connector 注册表：发现、开关（kill switch）与默认目录。"""

from __future__ import annotations

import os

from cg_connectors.base import BaseConnector
from cg_connectors.csv_source import CsvFixtureConnector
from cg_connectors.synthetic import SyntheticConnector

_REGISTRY: dict[str, BaseConnector] = {}


def register_connector(connector: BaseConnector) -> None:
    _REGISTRY[connector.spec().connector_id] = connector


def get_connector(connector_id: str) -> BaseConnector | None:
    """带停用开关：环境变量 CG_CONNECTOR_<ID>_ENABLED=false 时返回 None。"""
    connector = _REGISTRY.get(connector_id)
    if connector is None:
        return None
    flag = os.environ.get(f"CG_CONNECTOR_{connector_id.upper()}_ENABLED", "true")
    if flag.strip().lower() in {"0", "false", "no", "off"}:
        return None
    return connector


def list_connectors() -> list[BaseConnector]:
    return [c for c in _REGISTRY.values() if get_connector(c.spec().connector_id) is not None]


def register_defaults() -> None:
    if "synthetic" not in _REGISTRY:
        register_connector(SyntheticConnector())
    if "csv" not in _REGISTRY:
        register_connector(CsvFixtureConnector())


register_defaults()
