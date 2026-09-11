# 交付说明（DELIVERY）

交付日期：2026-09-08（v0.1.0）｜ v0.2（2026-09-11）：文档收敛 docs/、总览仪表板、模块边界 CI 强制、迁移指南（ADR-011/012）｜ v0.3（2026-09-12）：区域资本流动研究层——流动地图/流向线/桑基/趋势 + 流动性指标（ADR-013/014） ｜ 全部交付物位于 `资本图谱/` 子目录（ADR-010）

## 1. 架构与取舍（详见 ARCHITECTURE.md 与 docs/DECISIONS.md）

- **模块化单体 + 独立 worker + SPA**：FastAPI 一进程可服务 API 与前端静态产物；采集/重算走 `cg-worker`。
- **单一事实源 = 关系库**（SQLAlchemy 2.0，SQLite/PostgreSQL 双方言）；**图计算在 Python 层纯函数实现**
  （确定性、整数缩放比例、Fraction 聚合、显式护栏），不依赖任何图数据库递归方言（ADR-002）。
- **时态声明模型**：声明 + 证据链（document→snapshot(sha256)→fragment），修正走 supersede 不覆盖历史；
  持股与控制严格分开；UBO 只输出候选。
- 无 Docker 环境下的适配：本地默认 SQLite 零依赖运行；`infra/docker-compose.yml` 提供 PostgreSQL/生产形态。
- 未采用 Next.js（Vite SPA，ADR-007）、未采用 Dagster/Neo4j/DataHub（ADR-005 与 OSS_EVALUATION，均有触发条件）。

## 2. 已完成功能及文件

| 功能 | 位置 |
| --- | --- |
| 领域模型/时态声明/证据链/ORM | `packages/domain/src/cg_domain/`（orm.py、models.py、repo/） |
| 实体/标识符/别名检索；详情；声明历史；证据查询 | `apps/api/src/cg_api/routers/entities.py` |
| 向上/向下穿透、环路、交叉持股、聚合有效权益、UBO 候选（R1/R2 规则） | `packages/capital_graph/src/cg_capital_graph/`（engine.py、analysis.py） |
| 实体解析：规范化、USCC GB 32100 校验、评分、决策记录、合并 | `packages/entity_resolution/src/` + `packages/domain/normalization.py` |
| connector SDK：合规声明、限速、幂等键、失败隔离、内容寻址对象存储 | `packages/connectors/src/cg_connectors/`（base/storage/registry/ingest） |
| 合成演示数据（确定性种子，含环路/历史变更演示）与 CSV fixture 连接器 | 同上（synthetic.py、csv_source.py） |
| 幂等 worker（once/loop、指数退避、任务表） | `workers/src/cg_workers/worker.py` |
| RBAC（admin/analyst/viewer 默认拒绝）+ JWT + argon2id + 审计 + 限流 + 安全头 | `apps/api/src/cg_api/auth.py、ratelimit.py、main.py` |
| 图可视化：展开/收起、层数/阈值/方向/时间点、环路标红、UBO 标注、路径高亮、PNG/CSV 导出、超大图降级、动态实体类型图例与规模统计 | `apps/web/src/`（components/GraphCanvas.tsx、pages/Explore.tsx 等） |
| 数据总览仪表板：实体/声明/来源/复核/运行统计卡 + 类型/关系/年份/状态分布图表（纯 SVG，零新增依赖） | `apps/web/src/pages/Dashboard.tsx` + `routers/stats.py` |
| **资本流动研究层（v0.3）**：省际流向聚合（金额/笔数/有效权益、缺失显式计数）、区域流动性指标（净流入流出/HHI/环路资金/年度趋势）、省份→行业桑基 | `packages/capital_graph/src/cg_capital_graph/flows.py`、`apps/api/src/cg_api/routers/flows.py`、`routers/entities.py`(by-region) |
| 流动可视化：ECharts 中国地图 choropleth + 省际流向线（权重可切换）+ 排名/桑基/趋势图 + 省份下钻（明细与主体列表） | `apps/web/src/pages/Flows.tsx`、`components/EChart.tsx`、`assets/china.json`（来源声明见 assets/MAP_DATA_SOURCE.md） |
| 数据维度：entities.region_code/industry、statements.amount_scaled（万元×100 缩放整数），双方言迁移 | `packages/domain`（orm/models/repo）、`migrations/versions/a7c31e5b8d20_*` |
| 复核队列 + 质量问题 + 管理端（用户/审计/连接器） | `apps/web/src/pages/Review.tsx、Admin.tsx` + `routers/ops.py` |
| 迁移（含 ownership/control 视图，upgrade/downgrade 回环验证） | `migrations/` |
| 基础设施：Compose、Dockerfile、备份脚本、CI、SBOM、秘密扫描 | `infra/`、`scripts/`、`.github/workflows/ci.yml`、`docs/SBOM.cdx.json` |

## 3. 实际测试证据（详见 TEST_REPORT.md）

| 项 | 结果 |
| --- | --- |
| `uv run pytest tests --cov` | **80 passed**，退出码 0，TOTAL **89.9%**（v0.3） |
| `npm test`（vitest） | **8 passed**，退出码 0（v0.3） |
| `npx playwright test` | **8 passed**，退出码 0 |
| bandit / pip-audit / npm audit / secret_scan | 0 高危项；dev 链路余 2 moderate（已记录） |
| 性能 | 2990 边穿透 p95 2.4ms；500 节点环 28.8ms；错误率 0；确定性 ✓ |
| 恢复演练 | 备份→删库→恢复→行数一致 ✓ |
| 清洁环境复现 | `uv sync --frozen` → 迁移 → 种子 → 健康 → 鉴权 → 检索 全通过 |

## 4. 开源借鉴（详见 OSS_EVALUATION.md 与 THIRD_PARTY_NOTICES.md）

核实日期 2026-09-07（GitHub API）。运行时仅引入 **cytoscape.js（MIT）**；
followthemoney / BODS / nomenklatura / opensanctions / datahub / dagster 均为**模式借鉴，无代码复制**；
neo4j（GPL-3.0）未引入未链接。SBOM：`docs/SBOM.cdx.json`（110 组件）。

## 5. 启动与演示最短步骤（本机实测命令）

```bash
cd 资本图谱

# 后端（无需 Docker）
uv sync
uv run alembic upgrade head
uv run cg-seed --entities 40
CG_WEB_DIST=apps/web/dist uv run uvicorn cg_api.main:app --port 8300
# 前端（开发模式，另开终端；生产模式可跳过——后端已托管 dist）
cd apps/web && npm install && npm run dev
# 打开 http://localhost:5273 ，登录 viewer/viewer-demo-password
```

演示路径：检索"有限公司" → 打开任一企业 → 「查看」证据 → 「在穿透图中查看该主体」→
切换方向/时间点(2020-01-01 vs 当前) → 导出 CSV/PNG；用 admin 登录可看管理端与审计。

测试复现：`uv run pytest tests --cov`；`cd apps/web && npm test && npx playwright test`
（E2E 需后端已在 8300 运行）。

## 6. 已知限制

1. 单实例内存限流；JWT 无吊销列表（短时效缓解）。
2. SQLite 为默认开发库；生产建议 PostgreSQL（compose 就绪，迁移双方言兼容）。
3. 检索为规范化包含匹配，无中文分词（ADR-003 触发条件后再引入专用搜索）。
4. 图计算单进程内存受 `max_nodes` 护栏约束；超大规模需按 ADR-002 撤销条件引入投影缓存。
5. 交叉持股检测在节点集上有界（500/200 对），超出部分不承诺完整（THREAT_MODEL/DELIVERY 双记录）。
6. 首版未做：舆情/回测/真实交易（提示词范围外）；预留 `Security` 与事件标识接口。
7. 本会话未接入 DeepSeek 工具（ADR-008），全部代码由 ZCode 实现并自测。
