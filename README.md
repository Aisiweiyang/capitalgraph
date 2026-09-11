# CapitalGraph CN

[![CI](https://github.com/Aisiweiyang/capitalgraph-cn/actions/workflows/ci.yml/badge.svg)](https://github.com/Aisiweiyang/capitalgraph-cn/actions/workflows/ci.yml)
面向中国企业研究的资本关系、股权穿透、实际控制候选识别、历史变更追踪与证据可视化平台。

> 研究工具。所有穿透与 UBO 结果均为**候选**并附证据与算法假设，不构成法律认定或投资建议。

## 快速开始（本地开发，无需 Docker）

前置：uv（Python 3.12 由 uv 自动管理）、Node.js ≥ 20。

```bash
# 后端：安装 + 迁移 + 种子数据 + 启动
uv sync
uv run alembic upgrade head
uv run cg-seed --entities 40
uv run uvicorn cg_api.main:app --port 8300
# 健康检查: http://127.0.0.1:8300/api/v1/health
# OpenAPI:  http://127.0.0.1:8300/api/v1/docs

# 前端
cd apps/web && npm install && npm run dev   # http://localhost:5173

# 测试
uv run pytest
```

数据库默认 SQLite（`data/capitalgraph.sqlite3`，自动创建）；有 Docker 时可用
`docker compose -f infra/docker-compose.yml up -d` 启动 PostgreSQL，并在 `.env` 设置
`CG_DATABASE_URL=postgresql+asyncpg://cg:cg@localhost:5432/capitalgraph`。

## 演示账号（种子数据创建）

| 用户 | 口令 | 角色 |
| --- | --- | --- |
| admin | admin-demo-password | admin |
| analyst | analyst-demo-password | analyst |
| viewer | viewer-demo-password | viewer |

仅限本地演示；生产部署必须更换并配置 `CG_SECRET_KEY`。

## 文档

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) 架构与取舍
- [DATA_MODEL.md](docs/DATA_MODEL.md) 数据模型
- [docs/DECISIONS.md](docs/DECISIONS.md) ADR
- [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) 计划与验收
- [DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md) 数据合规
- [THREAT_MODEL.md](docs/THREAT_MODEL.md) 威胁模型
- [OSS_EVALUATION.md](docs/OSS_EVALUATION.md) 开源调研
- [TEST_REPORT.md](docs/TEST_REPORT.md) / [DELIVERY.md](docs/DELIVERY.md) 测试与交付证据
- [MIGRATION.md](docs/MIGRATION.md) 整体迁移与单模块抽取指南

## 目录

```
packages/domain             领域模型 + ORM + 迁移源（cg-domain）
packages/capital_graph      穿透/环路/交叉持股/聚合/UBO（cg-capital-graph，纯函数）
packages/entity_resolution  实体解析与决策记录（cg-entity-resolution）
packages/connectors         connector SDK + 合成数据 + CSV fixture（cg-connectors）
apps/api                    FastAPI 服务（cg-api）
apps/web                    React + TypeScript + Cytoscape.js 前端
workers                     幂等采集 worker（cg-workers）
migrations                  Alembic 迁移
tests                       单元/集成/安全/性能测试
infra                       docker-compose、备份脚本
scripts                     演示、备份、SBOM、扫描脚本
```

## 许可证

Apache-2.0（见 LICENSE；第三方组件见 THIRD_PARTY_NOTICES.md）
