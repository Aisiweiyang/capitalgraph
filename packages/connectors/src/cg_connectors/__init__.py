"""connector SDK 与内置数据源。

合规基线（DATA_GOVERNANCE.md）：
- 只接入公开/授权/合成数据；不触碰登录、验证码、付费墙。
- 每个 connector 声明 ConnectorSpec（允许用途、速率、robots、开关）。
- 运行器提供速率限制、失败隔离、幂等键；原文持久化可配置关闭。
"""

from cg_connectors.base import (
    BaseConnector,
    ConnectorContext,
    ConnectorResult,
    IngestionIssue,
)
from cg_connectors.csv_source import CsvFixtureConnector
from cg_connectors.registry import get_connector, list_connectors, register_connector
from cg_connectors.storage import LocalObjectStore, ObjectStore
from cg_connectors.synthetic import SyntheticConnector

__all__ = [
    "BaseConnector",
    "ConnectorContext",
    "ConnectorResult",
    "CsvFixtureConnector",
    "IngestionIssue",
    "LocalObjectStore",
    "ObjectStore",
    "SyntheticConnector",
    "get_connector",
    "list_connectors",
    "register_connector",
]
