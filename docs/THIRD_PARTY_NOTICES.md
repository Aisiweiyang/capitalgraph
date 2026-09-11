# 第三方组件与许可证声明（THIRD_PARTY_NOTICES）

运行时第三方库清单以 `docs/SBOM.cdx.json` 为准（生成脚本 `scripts/sbom.py`）。以下为主要组件及其许可证。

## Python 运行时依赖（uv.lock 锁定）

| 组件 | 许可证 | 用途 |
| --- | --- | --- |
| fastapi / starlette | MIT | Web 框架 |
| uvicorn | BSD-3-Clause | ASGI 服务器 |
| pydantic / pydantic-settings | MIT | 数据校验 |
| SQLAlchemy | MIT | ORM |
| alembic | MIT | 数据库迁移 |
| aiosqlite | MIT | SQLite 异步驱动 |
| asyncpg（可选 extra） | Apache-2.0 | PostgreSQL 异步驱动 |
| PyJWT | MIT | JWT 令牌 |
| argon2-cffi | MIT | 口令哈希（argon2id） |
| orjson | MIT/Apache-2.0 | JSON 序列化 |
| click / h11 / anyio 等传递依赖 | MIT/BSD/Apache-2.0 | 见 SBOM |

## 前端运行时依赖（package-lock.json 锁定）

| 组件 | 许可证 | 用途 |
| --- | --- | --- |
| cytoscape | MIT | 交互式网络图（提示词 §3 指定采用） |
| react / react-dom | MIT | UI 框架 |
| react-router-dom | MIT | 路由 |

## 开发工具链（不随产物分发）

pytest、pytest-asyncio、pytest-cov（MIT）、ruff（MIT）、mypy（MIT）、httpx（BSD-3-Clause）、
vite（MIT）、vitest（MIT）、@playwright/test（Apache-2.0）、TypeScript（Apache-2.0）、
eslint 系（MIT）、@testing-library/*（MIT）。

## 模式借鉴（无代码复制，见 OSS_EVALUATION.md）

- alephdata/followthemoney（MIT）：实体本体与验证思想。
- openownership/data-standard（Apache-2.0）：BODS 声明/证据语义参考。
- opensanctions/nomenklatura（MIT）：实体解析决策记录语义参考。
- opensanctions/opensanctions（代码 MIT）：采集管线与质量报告模式。
- datahub-project/datahub（Apache-2.0）与 dagster-io/dagster（Apache-2.0）：治理/编排思想，未引入。

## 许可证边界

- 本项目自身代码：Apache-2.0（见 LICENSE）。
- neo4j Community（GPL-3.0）：**未引入、未链接**；仅作为可选独立部署形态记录于 ADR-002。
- 各数据源的内容许可独立于代码许可，connector 必须在 `ConnectorSpec` 中声明（DATA_GOVERNANCE.md）。
