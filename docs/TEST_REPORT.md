# 交付说明（DELIVERY）

交付日期：2026-09-08（v0.1.0）｜ v0.2（2026-09-11）：文档收敛 docs/、总览仪表板、模块边界 CI 强制、迁移指南（ADR-011/012）｜ v0.3（2026-09-12）：区域资本流动研究层——流动地图/流向线/桑基/趋势 + 流动性指标（ADR-013/014）｜ v0.3.1：使用与自定义指南(docs/USER_GUIDE.md)、启动演示.cmd 一键脚本、CSV 自备数据支持省份/行业/金额列+模板、穿透图页内检索 ｜ 全部交付物位于 `资本图谱/` 子目录（ADR-010）

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
6. 首版未做：舆情/回测/真实交易（首版范围外）；预留 `Security` 与事件标识接口。

## v0.4 实测记录（2026-09-13，Windows 11 本机）

### 功能与文件位置

| 切片 | 文件 |
| --- | --- |
| A 系族识别 | `packages/capital_graph/src/cg_capital_graph/families.py`（纯函数）；`apps/api/src/cg_api/routers/families.py`；`apps/web/src/pages/Families.tsx` + `components/FamilyGraph.tsx` |
| B 风险传导 | `.../cg_capital_graph/risk_chains.py`（纯函数）；`.../cg_api/routers/risk.py`；`cg_domain/enums.py`（FlagType 扩展）、`repo/ops.py`（list_risk_flags/open_risk_flag_subjects）；`cg_connectors/synthetic.py`（链式/环式担保圈+质押场景）、`csv_source.py`（record_type 扩展）；`apps/web/src/pages/Entity.tsx`（风险传导区）、`Review.tsx`（风险标记）、`riskDisplay.ts` |
| C 按年回放 | `apps/web/src/replay.ts`（纯逻辑）+ `pages/Flows.tsx`（回放控件与帧渲染） |
| D 报告导出 | `apps/web/src/report.ts` + Explore/Flows/Families 三页「导出报告」按钮 + `components/EChart.tsx`/`GraphCanvas.tsx` 图表句柄 |
| 测试 | `tests/capital_graph/test_families.py`(15)、`test_risk_chains.py`(10)、`tests/api/test_families_api.py`(8)、`test_risk_api.py`(10)、`tests/connectors/test_csv.py`(新增3)；前端 `Families.test.tsx`(3)、`riskDisplay.test.ts`(3)、`replay.test.ts`(4)、`report.test.ts`(4)、`Flows.test.tsx`(+2) |

### 实际命令与结果（全部本机实测）

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests --cov --cov-report=term -p no:warnings` | **129 passed**，退出码 0，TOTAL **91.3%**（基线 83 项/89%→129 项/91.3%，零回归） |
| `cd apps/web && npx vitest run` | **24 passed**（7 文件），退出码 0（基线 8 项 → 24 项） |
| `npx tsc -b && npm run build` | 类型检查通过，vite 构建成功 |
| `CG_API_PROXY=… npx playwright test` | **8 passed**（19.0s；E2E 后端临时跑在 8301，经 vite 代理） |
| `uv run python scripts/module_graph.py` | 模块边界校验通过 |
| `uv run python scripts/secret_scan.py` | 未发现疑似硬编码密钥 |
| `uvx bandit -q -r packages apps/api/src workers/src` | 退出码 0，无告警 |
| `alembic upgrade head → downgrade base → upgrade head` | 迁移回环通过（SQLite） |

### 开源借鉴（详见 OSS_EVALUATION.md v0.4 增量）

- networkx（BSD-3）：**复核后仍自研**——union-find/BFS/DFS 足够，保持纯函数零依赖（ADR-015）；
- antvis/G6（MIT）：**评估后不引入**——Cytoscape breadthfirst + 区域着色满足系族子图（ADR-015）；
- 零新增后端 Python 运行时依赖。

### 已知限制与下一步建议

1. 系族聚类以"共同可达成员"并族，未做社群最优化（Louvain）；万级成员场景需重估（ADR-015 触发条件）。
2. 风险传导为 BFS 逐层扩散的保守口径，未做金额加权概率模型；出险定义=被标 RiskFlag，实为研究假设。
3. 回放为前端逐帧预取（年数×2 请求），年份数很大时建议后端批量接口（现规模 ≤ 十年×2 无压力）。
4. 报告导出为纯前端快照，不含证据原文（后续可加证据表 deep-link）。
5. E2E 未覆盖新页面（families/risk/replay 为集成+单测覆盖）；可按需补 Playwright 用例。

## v0.5 实测记录（2026-09-14，Windows 11 本机）

### 功能与文件位置

| 切片 | 文件 |
| --- | --- |
| A 变更事件流 | `packages/capital_graph/src/cg_capital_graph/events.py`（diff_events/events_for_entity 纯函数）；`apps/api/src/cg_api/routers/events.py`（/events、/events/types）+ `routers/entities.py`（/{id}/events）；`apps/web/src/pages/Events.tsx`（异动页）、`Entity.tsx`（变更轨迹区）、`eventsDisplay.ts`（展示口径） |
| B 格局对比 | `packages/capital_graph/src/cg_capital_graph/compare.py`（diff_families/compare_flows，未改动 families.py/flows.py 既有签名）；`routers/families.py`（/compare）+ `routers/flows.py`（/flows/compare）；`Families.tsx`/`Flows.tsx` 对比模式、`compareDisplay.ts`、`report.ts` compare 上下文 |
| C 证据工作台 | `packages/capital_graph/src/cg_capital_graph/evidence.py`（evidence_coverage 纯函数）；`apps/api/src/cg_api/routers/evidence.py`（coverage/documents/lookup）+ `repo/statements.py`（evidence_coverage_rows/evidence_documents）；`apps/web/src/pages/Evidence.tsx`、`components/EvidenceTable.tsx`、`evidenceDisplay.ts`；deep-link：Explore/Families/Review/Events/Entity；报告证据表 `report.ts`+`reportEvidence.ts` |
| D 质量收尾 | `apps/web/e2e/v05-pages.spec.ts`（8 项新 E2E）；`tests/performance/test_v05_perf.py`；顺带修复 `cg_connectors/synthetic.py` 分批缺陷与 `ingest.py` 证据静默丢失（见 ADR-018） |

### 实际命令与结果（全部本机实测）

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests --cov --cov-report=term -p no:warnings` | **179 passed**，退出码 0，TOTAL **92.3%**（基线 129 项/91.3% → 179 项/92.3%，零回归；新增 50 项 = 事件 23 + 对比 17 + 证据 9 + 性能基线 1） |
| `cd apps/web && npx vitest run` | **42 passed**（10 文件），退出码 0（基线 24 项 → 42 项） |
| `npx tsc -b && npm run build` | 类型检查通过，vite 构建成功 |
| `CG_API_PROXY=http://127.0.0.1:8301 npx playwright test` | **16 passed**（17.8s；基线 8 项 + 新增 8 项，零回归） |
| `uv run ruff check packages apps workers tests` / `ruff format --check` | 全部通过 |
| `uv run python scripts/module_graph.py` | 模块边界校验通过 |
| `uv run python scripts/secret_scan.py` | 未发现疑似硬编码密钥 |
| `uvx bandit -q -r packages apps/api/src workers/src` | 退出码 0，无告警 |

### 性能基线（切片 D，2000 声明规模）

`uv run pytest tests/performance/test_v05_perf.py -q -s`（seed=42 确定性合成，实体 640 →
**声明 2008**，窗口 2020-01-01→2024-01-01，各 5 次取 p50/max）：

| 端点 | p50 | max |
| --- | --- | --- |
| `/api/v1/events`（窗口内 2 事件） | 32.5 ms | 62.2 ms |
| `/api/v1/families/compare` | 58.2 ms | 103.6 ms |
| `/api/v1/flows/compare` | 74.3 ms | 116.1 ms |

环境：AMD64 / Python 3.12.13 / Windows。远低于穿透护栏超时（10s）；断言仅护栏级，
超阈值只记录并在已知限制说明，不阻塞交付。

### 开源借鉴（详见 OSS_EVALUATION.md v0.5 增量）

- deepdiff（MIT）：**自研不引入**——键集合 diff 约百行且需业务口径（比例缺失显式不比较）；
- 时间线组件库：**自研**（HTML/CSS 列表 + chips），零新增前端依赖；
- 事件溯源/CQRS 框架：**不引入**（事件为派生只读视图，无写入路径需求）；
- 零新增后端 Python 运行时依赖（ADR-002/014/015 路线保持）。

### 已知限制与下一步建议

1. 事件为两时点集合差异派生，不含 recorded_at 粒度的中间历史（如需逐日事件可按月切片查询）。
2. 同键多条声明部分重叠时比例事件退化为增删事件（归因歧义，口径见 ADR-017）。
3. /events 全量分页加载两时点快照后内存对比，千万级声明需引入数据库侧 diff 或游标分片。
4. 覆盖率只统计"有无证据片段"，不评估证据内容质量/时效（stale_source 已有 QualityIssue 通道）。
5. 报告证据表上限 200 条声明（lookup 单次上限），更大报告需分批导出。

## v0.5.1 优化记录（2026-09-14，前端性能与体验，后端零改动）

### 优化内容与动机

| 项 | 动机（v0.5 已知状态） | 改动 |
| --- | --- | --- |
| A 路由级代码分割 | 单 chunk 1,901.85KB（gzip 627.19KB），构建即告警 | App.tsx 全部页面路由 React.lazy + Suspense；echarts/cytoscape 以 manualChunks 独立命名 vendor chunk；chunkSizeWarningLimit 1200 并注释理由 |
| B 报告证据分批 | /evidence/lookup 单次 200 条上限截断报告证据表 | reportEvidence.ts：chunkIds 纯函数按 200 切批（与后端上限一致），总上限提升至 1000 条；批间合并；任一批失败整体降级为无证据表 |
| C 异动页分页 | 一次性拉 500 条做客户端过滤 | 类型筛选改服务端 event_type 参数；"加载更多"offset/limit 分页（页大小 100）；eventsDisplay 移除客户端 filterEvents |
| D 变更轨迹窗口可调 | 实体页变更轨迹窗口硬编码 | from/to 日期选择写入 URL 查询参数（events_from/events_to，replace 导航）支持深链；窗口内无事件显式空态 |

### 构建体积实测（npm run build）

| 指标 | v0.5（前） | v0.5.1（后） |
| --- | --- | --- |
| 首屏 JS（index） | 1,901.85 KB / gzip 627.19 KB | **175.88 KB / gzip 58.08 KB（−90.7%）** |
| echarts（懒加载，Flows 等页触发） | 混在主包 | vendor-echarts 627.66 KB / gzip 205.46 KB |
| cytoscape（懒加载，穿透/系谱页触发） | 混在主包 | vendor-cytoscape 434.85 KB / gzip 137.78 KB |
| 页面 chunk | 无 | 每页 0.6–15 KB 级（Search/Admin/Events/Review/Dashboard/Evidence/Entity/Explore/Families/Flows） |

### 实际命令与结果（全部本机实测）

| 命令 | 结果 |
| --- | --- |
| `cd apps/web && npx tsc -b && npm run build` | 类型检查通过，构建成功（体积见上表） |
| `cd apps/web && npx vitest run` | **50 passed**（11 文件；基线 42 → 50，新增 reportEvidence 分批 8 项，移除客户端筛选用例） |
| `CG_API_PROXY=… npx playwright test` | **16 passed**（全部既有用例保持通过） |
| `uv run pytest tests --cov -q -p no:warnings` | **179 passed / 92.3%**（后端零改动，复跑确认） |
| `uv run ruff check / format --check` | 通过（本轮无后端改动） |

### 回归根因记录（E2E 选择器收窄）

路由懒加载引入竞态：React Router 在新路由 chunk 加载期间保留旧页面 UI（transition 语义），
实体页新增的日期输入（变更轨迹窗口）与 core-flow「切换历史时间点」的通用选择器
`input[type="date"]` 冲突（穿透页自身输入尚未挂载）。处理：穿透图页时间点输入增加
`data-testid="explore-at"`，该用例选择器收窄至页内专属 testid（断言语义不变：切换后
侧栏标题含时点）。其余 15 项用例零改动通过。

## v0.6 实测记录（2026-09-15，Windows 11 本机）

范围：覆盖率趋势（ADR-019）+ 证据时效规则（ADR-020）+ 数据链路（captured_at）+
报告时效标注/覆盖率摘要 + 前端证据工作台趋势区/时效区 + E2E 与性能基线。
基线 v0.5.1：后端 179 passed / 92.3%，前端 50 passed，E2E 16 passed。

### 切片 A/B/C（后端与前端逻辑）

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests -q -W ignore` | **203 passed**，退出码 0（基线 179 → 203，+24：coverage_timeline 纯函数 6、GET /coverage/timeline 3、stale_evidence 纯函数 6、repo max(fetched_at) 2、/staleness 与 /staleness/scan API 6、性能基线 1），既有断言零回归 |
| `cd apps/web && npx tsc -b` | 类型检查通过（修复 Flows 导出按钮 async 块闭合 + report.test.ts fixture 补 fetched_at） |
| `cd apps/web && npx vitest run` | **60 passed**（11 文件），退出码 0（基线 50 → 60：趋势/时效展示 6、报告快照列/陈旧标注/覆盖率摘要/边界 4） |

### 切片 D（E2E 与性能基线）

E2E 种子库按惯例重建（`rm data/e2e-v05.sqlite3 && CG_DATABASE_URL=… CG_API_PROXY 代理
8301`）：`python -m cg_api.seed --entities 40 --seed 40` → 140 声明，建库后校验
`source_snapshots`：**仅质押 1 条 fetched_at=2019-01-01，其余 139 条为建库当日**（captured_at
回填生效，旧库无迁移、语义兼容）。

| 命令 | 结果 |
| --- | --- |
| `CG_API_PROXY=http://127.0.0.1:8301 npx playwright test` | **19 passed**（14.3s；基线 16 + 新增 3：趋势区渲染、时效区候选表/空态切换、viewer 视角扫描按钮 RBAC 提示），零回归。首轮因后端默认限流 120/分触发 1 次 429（用例数增多导致），E2E 后端改以 `CG_RATE_LIMIT_PER_MINUTE=1200` 启动后全绿（已记录 USER_GUIDE §9） |
| `uv run pytest tests/performance/test_v06_perf.py -q -s` | 通过（见下方基线） |

### 性能基线（切片 D，2008 声明规模）

`uv run pytest tests/performance/test_v06_perf.py -q -s`（seed=42 确定性合成，实体 640 →
**声明 2008**，各 5 次取 p50/max；趋势年度数=2，5 年阈值候选=1）：

| 端点 | p50 | max |
| --- | --- | --- |
| GET /evidence/coverage/timeline | 15.9 ms | 89.9 ms |
| GET /evidence/staleness?years=5 | 20.7 ms | 25.9 ms |

（AMD64 / Python 3.12.13 / Windows；只读全量扫描型端点，护栏与 v0.5 同数量级——
默认超时 10s 级别，实际低 1–2 个数量级。）

### 安全与其他

| 项 | 结果 |
| --- | --- |
| `uv run python scripts/module_graph.py` | 模块边界校验通过 |
| RBAC | /staleness/scan 写通道 analyst+（viewer 401/403 断言在 API 测试内），只读端点 viewer 可读 |
| 幂等 | /staleness/scan 重复执行 created=0/skipped=N 断言（API 测试） |

### 已知限制与口径提示

1. 时效规则只提示不认定（ADR-020）；快照缺省取证时间为入库时间，旧库语义自然兼容。
2. 覆盖率趋势按生效年度分组，年度差值不构成质量改进/恶化的认定（声明集合随时点变化）。
3. 报告证据表上限 1000 条（分批收集），覆盖率摘要与陈旧标注获取失败均降级省略。
4. E2E 用例增多后需提高 E2E 后端限流限额（见 USER_GUIDE §9），生产限流策略不变。

## v0.6.1 维护记录（2026-09-16，依赖更新与去过程化整理，无功能变更）

范围：前端依赖安全升级、Python 锁文件升级、证据工作台请求合并、开发过程档案移出仓库。
基线 v0.6：后端 203 passed / 92.7%，前端 60 passed，E2E 19 passed。

| 命令 | 结果 |
| --- | --- |
| `npm install echarts@^6.1.0 react-router-dom@^7.18.4`（apps/web） | echarts 5.6→6.1（修 XSS 公告 GHSA-fgmj-fm8m-jvvx）、react-router-dom 6.30→7.18（修 GHSA-wrjc-x8rr-h8h6 等 2 项），`npm audit` **0 vulnerabilities**（此前 3 moderate）；tsc 与 vitest 60 passed 零改动通过，E2E 19 passed 验证路由行为 |
| `npm install -D jsdom@^30.0.1 @testing-library/jest-dom@^7.0.1` | 开发依赖跟上当前主版本，60 passed |
| `uv lock --upgrade && uv sync` | greenlet/pyjwt/ruff/sqlalchemy/uvicorn 小版本升级，全量后端复跑通过 |
| `uvx pip-audit` | No known vulnerabilities |
| `uv run pytest tests --cov -p no:cacheprovider -W ignore` | **204 passed / 92.7%**（+1：/coverage 内嵌 timeline 一致性测试） |
| `cd apps/web && npx tsc -b && npm run build` | 通过；vendor-echarts 懒加载块 627.66→668.06 KB（gzip 205.46→222.74），首屏 176.37→191.28 KB（gzip 58.16→63.35），为安全版本代价；仍按页懒加载 |
| `CG_API_PROXY=http://127.0.0.1:8301 npx playwright test` | **19 passed**（12.6s） |
| ruff check / format、secret_scan、module_graph | 全部通过 |

### 请求合并（一处小的性能整理）

证据工作台原来挂载时发 4 个请求，其中 /evidence/coverage 与 /evidence/coverage/timeline
在服务端是同一次声明扫描跑两遍。现 /coverage 响应附带 timeline 字段（同一次扫描顺带
产出，加法式变更），前端改为一次请求同时渲染覆盖率与趋势；独立端点 /coverage/timeline
保留（一致性有测试断言）。

## v0.6.2 维护记录（2026-09-16，前端 lint 工程 + CI 现代化 + 补测试，无功能变更）

范围：把一直处于损坏状态的 `npm run lint` 修活并接入 CI，升级 CI actions 版本，
为覆盖率最低的两个模块补齐单元测试。基线 v0.6.1：后端 204 passed / 92.7%。

| 命令 | 结果 |
| --- | --- |
| `npm run lint`（新增 eslint.config.js + devDependencies） | **0 errors / 18 warnings**（均为已知模式：挂载取数触发 set-state-in-effect 提示、组件文件导出常量的 fast-refresh 提示），脚本此前引用未安装的 eslint，从未真正可运行 |
| `uv run pytest tests --cov -p no:cacheprovider -W ignore` | **214 passed / 94.1%**（+10 项：scoring 边界 8、seed 幂等 2；覆盖率 92.7% → 94.1%，seed.py 0% → 全覆盖，scoring.py 80.4% → 全覆盖） |
| `CG_API_PROXY=http://127.0.0.1:8301 npx playwright test` | **19 passed**（17.1s） |
| `cd apps/web && npx tsc -b && npm run build && npx vitest run` | 通过，60 passed |
| ruff check / format、secret_scan、module_graph | 全部通过 |

### 新增测试

- `tests/entity_resolution/test_scoring.py`（8 项）：单一标识符只进复核带（0.60 < 0.90）、
  标识符 + 佐证恰好 0.90 判 merge、短名分支与完全一致互斥、相似度 0.85 入分/0.84 不入、
  无标识符的满分仍只复核、权重和截断到 1.0、自定义阈值边界（≥ 语义）、确定性；
- `tests/api/test_seed.py`（2 项）：种子幂等（二次执行三计数均零）、显式 database_url
  优先于环境变量（本轮修复：原先 `setdefault` 会静默忽略显式参数，环境变量已存在时
  种子可能写错库）。

### CI 变更

- actions/checkout v4→v7、actions/setup-node v4→v7、astral-sh/setup-uv v5→v10
  （清除 Node 20 弃用告警）；
- frontend job 新增 `npm run lint` 步骤；npm audit 步骤移除 `|| true`
  （依赖已清零，high+ 出现时应当真实失败）。

## v0.6.3 维护记录（2026-09-16，响应压缩 + 小版本跟进，无功能变更）

范围：API 与静态托管启用 gzip，跟进 vite 小版本，顺带核验了索引与查询匹配情况。
基线 v0.6.2：后端 214 passed / 94.1%。

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests --cov -p no:cacheprovider -W ignore` | **216 passed / 94.3%**（+2：gzip 压缩断言与阈值行为） |
| `CG_API_PROXY=http://127.0.0.1:8301 npx playwright test` | **19 passed**（14.7s） |
| `npm update vite`（8.2.2→8.3.0）+ build / lint / vitest | 通过，60 passed，npm audit 0 |
| ruff check / format、secret_scan、module_graph | 全部通过 |

### 响应压缩实测（2008 声明规模，GZipMiddleware minimum_size=1024）

| 端点 | 原始 | 传输（gzip） | 比 |
| --- | --- | --- | --- |
| /events（100 条页） | 48,669 B | 8,257 B | **5.9×** |
| /evidence/coverage | 1,342 B | 610 B | 2.2× |
| /evidence/staleness | 978 B | 978 B | 未压缩（低于阈值，符合设计） |

### 顺带核验（无需改动）

- ORM 索引与热查询匹配完整（statements 的 subject/object/temporal 组合索引、
  evidence 链路各外键索引均已存在）；
- repo 层批量反查均为单条 IN 查询，无 N+1。

## v0.7 实测记录（2026-09-16，Windows 11 本机）

范围：质量规则族（有效性 / 唯一性 / 跨源一致性）+ /evidence/quality 五维度总览 +
工作台质量总览区 + E2E + 性能基线。基线 v0.6.3：后端 216 passed / 94.3%。

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests --cov -p no:cacheprovider -W ignore` | **228 passed / 94.4%**（+12：质量纯函数 7、质量 API 4、性能基线 1），既有断言零回归 |
| `cd apps/web && npx tsc -b && npm run lint && npx vitest run` | 通过 / 0 errors / **60 passed** |
| `CG_API_PROXY=http://127.0.0.1:8301 npx playwright test` | **20 passed**（13.4s；基线 19 + 质量总览 1） |
| `uv run pytest tests/performance/test_v07_perf.py -q -s` | 通过（见下方基线） |
| ruff check / format、secret_scan、module_graph、npm audit、pip-audit | 全部通过 |

### 性能基线（2008 声明规模，各 5 次取 p50/max）

| 端点 | p50 | max |
| --- | --- | --- |
| GET /evidence/quality（五维度总览，内部 4 次只读扫描） | 53.4 ms | 55.8 ms |

counts（seed=42，640 实体）：coverage_missing=0 / staleness=1（质押 2019-01-01）/
validity=0 / uniqueness=0 / consistency=0。（AMD64 / Python 3.12.13 / Windows）

### 合成库上的真实候选（规则自检）

- 合成连接器有"必须产出合法 USCC"的生成器不变量 → 有效性候选恒为 0（规则由
  API 测试内直接注入非法标识符验证捕获）；
- 12 实体规格下转移场景存在同键两条 holds_shares → 唯一性规则如实标出 1 组
  （确定性，API 测试断言）；该候选属"需人工甄别"范畴，符合只提示不认定口径。

## v0.7.1 维护记录（2026-09-16，可视化与流动感抛光，零功能/零依赖变更）

范围：路由过渡与悬停动效、路由加载反馈、流向线拖尾特效、趋势图抛光、穿透图布局动画。
基线 v0.7：后端 228 passed / 94.4%，前端 60，E2E 20。

| 命令 | 结果 |
| --- | --- |
| `cd apps/web && npx tsc -b && npm run lint && npx vitest run` | 通过 / 0 errors / 60 passed |
| `npm run build` | 成功，体积不变（纯 CSS 动效，零新依赖） |
| `CG_API_PROXY=http://127.0.0.1:8301 npx playwright test` | **20 passed**（14.2s），画布类用例（穿透图/回放/导出）零回归 |
| ruff、secret_scan、module_graph | 通过（后端零改动） |

### 动效清单

- **样式动效层**：面板进场（fade+上移 0.28s）、计数卡悬停浮起、按钮/导航与表格行
  过渡、路由加载脉冲反馈（PageFallback 样式化）；全局响应
  `prefers-reduced-motion: reduce`（减弱动效偏好下全部退化为瞬时）；
- **流向线拖尾**：省际流向线开启 effect 拖尾（统一 60px/s、trailLength 0.35）。
  保留两条既有约束——入场动画仍关闭（后台标签页 rAF 节流导致整线不可见的原修复）、
  progressive: 0（导出可见性）；拖尾叠加在静态线之上，后台冻结仅损失动效不损失内容；
- **趋势图抛光**：覆盖率趋势线平滑 + 面积渐变 + 数据点标记（vitest 断言的
  轴/数据结构未动）；
- **穿透图**：breadthfirst 布局节点滑入就位（300ms），替代瞬现。

## v0.7.2 维护记录（2026-09-16，测试套件提速 + lifespan 现代化，零功能变更）

范围：套件耗时 171s → **108s**（含覆盖率插桩；裸跑 95s，−37%），消除自身代码的
FastAPI on_event 弃用告警。基线 v0.7.1：后端 228 passed / 94.4%。

| 命令 | 结果 |
| --- | --- |
| `time uv run pytest tests --cov -p no:cacheprovider -W ignore` | **228 passed / 94.4%**，171s → **108s** |
| `uv run pytest tests/performance -q` | 5 项全绿（共享建库后仍覆盖原三端点组断言） |
| `CG_API_PROXY=… npx playwright test` | **20 passed**（lifespan 在 uvicorn 下启动/健康检查实测正常） |
| ruff check / format、secret_scan、module_graph | 全部通过 |

### 提速来源

1. **性能基线共享建库**（约 −63s）：v0.5/v0.6/v0.7 三份性能用例此前各自建一套
   2008 声明库（seed=42 同源同规模，约 36s/次）；收敛到
   `tests/performance/conftest.py` 会话级夹具后只建一次。各用例的断言与输出格式不变；
2. **argon2 成本可配**（约 −13s）：`CG_ARGON2_TIME_COST / MEMORY_COST / PARALLELISM`
   环境变量（默认与 argon2-cffi 库默认一致，生产行为不变）；tests/conftest.py 在
   cg_api.auth 导入前降档（time=1/mem=8MB/p=1）——单测大量建用户+登录，默认档位
   每次哈希数百毫秒。校验安全性不受影响：argon2 编码串自带参数，verify 按串内参数执行；
3. **lifespan 迁移**：`@app.on_event` → FastAPI lifespan（asynccontextmanager），
   消除自身代码的 StarletteDeprecationWarning；剩余 3 条告警均为 fastapi/starlette
   库内部实现（testclient/httpx、anyio 别名、HTTP_422 常量），待上游发版自然消除。

## v0.7.3 维护记录（2026-09-16，mypy 全仓拉零 + 潜伏缺陷修复 + 取数竞态，零功能变更）

范围：把 dev 依赖里从未执行过的 mypy 全仓跑通并接入 CI；过程中揪出并修复一个潜伏
仓储缺陷；修复前端阈值切换的取数竞态。基线 v0.7.2：228 passed / 94.4%。

| 命令 | 结果 |
| --- | --- |
| `uv run mypy packages/*/src apps/api/src workers` | **0 errors（55 文件）**：修复 12 处（domain 1 / capital_graph 7 / api 4），CI 新增 mypy 步骤强制不回退 |
| `uv run pytest tests --cov -p no:cacheprovider -W ignore` | **233 passed / 94.5%**（+5：user_count 回归 1、storage 原子性 4） |
| `cd apps/web && npx tsc -b && npm run lint && npx vitest run` | 通过 / 0 errors / 60 passed |
| `CG_API_PROXY=http://127.0.0.1:8301 npx playwright test` | **20 passed** |
| ruff check / format、secret_scan、module_graph | 全部通过 |

### mypy 揪出的潜伏缺陷（真实 bug，非仅类型问题）

- **repo.user_count**：`await self.session.execute(...).scalar_one()`——await 优先级低于
  属性访问，实际对协程对象调 `.scalar_one()`，一旦被调用必然 AttributeError。因无任何
  调用方而潜伏至今（admin stats 端点内联了正确实现）。已修复并补调用测试防回归；
- 其余 11 处为类型表达问题（dict(Row) 解包、混合类型 payload、联合键 get），行为本就
  正确，改为显式类型注解/生成器解包/幂等 str() 转换。

### 前端取数竞态

证据工作台的时效区与质量总览随阈值变化重新取数，原先快速连续切换阈值时，慢的旧响应
可能乱序返回覆盖新结果。现以 AbortController 在 effect 清理时中止旧请求，并忽略
AbortError 不误置空态。

### storage 原子性测试

补 LocalObjectStore 异常分支：内容寻址去重（同内容单文件）、缺键 FileNotFoundError、
删除幂等、写失败（os.replace 注入故障）后无临时文件/半写对象残留。

## v0.7.4 维护记录（2026-09-16，测试套件并行化 + 防御分支补测，零功能变更）

范围：pytest-xdist 按文件并行接入本地与 CI；补 db/normalization 防御性分支至 100%。
基线 v0.7.3：233 passed / 94.5%，套件 108s。

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests --cov -q -n auto --dist loadfile` | **237 passed / 94.7%**，含覆盖率插桩 **108s → 55s（2×）**；裸跑三轮 44–45s 稳定全绿 |
| `uv run mypy …`（全仓）/ ruff / secret_scan / module_graph | 全部通过 |

### 并行化要点

- `--dist loadfile`：同一测试文件固定在同一 worker，模块级 fixture 与进程内
  CG_DATABASE_URL 环境设定不会跨文件互踩；
- pytest-cov 原生支持 xdist 覆盖率合并，CI 报告数字与顺序执行一致；
- 性能护栏（max_ms < 10s 级）实测并行负载下 p50/max 量级不变，离护栏两个数量级。

### 补测（+4，db.py / normalization.py 均至 100%）

- 空名/纯空白 normalize、USCC 字符集外字符（I/O/S/V/Z）判非法；
- make_engine 非 sqlite 分支（mock create_async_engine 验参数，
  pool_pre_ping 保留断言；环境无 asyncpg 驱动，真实构造留给集成）；default_database_url 兜底值。

## v0.7.5 维护记录（2026-09-16，写通道端到端 + CI 缓存 + 收尾补测，零功能变更）

范围：补上 analyst"扫描入库"写通道的端到端覆盖（此前只有 API 级断言）；CI frontend
job 接入 npm 缓存；registry/regions 防御分支补测。基线 v0.7.4：237 passed / 94.7%。

| 命令 | 结果 |
| --- | --- |
| `CG_API_PROXY=… npx playwright test` | **21 passed**（新增 analyst 扫描入库用例；连续两轮重跑验证幂等断言与库状态无关，可重复执行） |
| `uv run pytest tests --cov -q -n auto --dist loadfile` | **239 passed / 94.8%**（+2：registry 环境开关、regions 代码校验） |
| ruff / format / mypy / secret_scan / module_graph（CI 同命令） | 全部通过 |

### analyst 写通道 E2E（v07-staleness-scan.spec.ts）

页内登录 analyst 换 token 后刷新：viewer 的角色提示消失、"扫描入库"按钮出现 → 点击 →
结果行"已入库 N 条（跳过重复 M 条）· 规则 stale_source" → 重复点击全部 skipped（幂等
端到端验证）。断言与库历史状态无关，E2E 库无需重置。

### CI

- frontend：setup-node 开启 `cache: npm`（锁文件路径 apps/web/package-lock.json）；
- 核验确认后端 ruff 规则已含 B/SIM/UP/C4 全量族且零告警，无需再收严。

## v0.8 实测记录（2026-09-16，质量登记闭环）

范围：POST /evidence/quality/scan 统一登记端点 + 工作台"登记复核"入口 + 端到端。
基线 v0.7.5：后端 239 passed / 94.8%，前端 60，E2E 21。

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests --cov -q -n auto --dist loadfile` | **242 passed / 94.8%**（+3：scan RBAC/幂等增量、审计落库；修复中顺带补 analyst 种子用户） |
| `cd apps/web && npx tsc -b && npm run lint && npx vitest run` | 通过 / 0 errors / **61 passed**（+1 qualityScanText） |
| `CG_API_PROXY=… npx playwright test` | **22 passed**（+1：analyst 登记按钮端到端 created→skipped，与库状态无关可重复） |
| ruff / format / mypy / secret_scan / module_graph | 全部通过 |

幂等语义：有效性按实体（同实体多候选只登记一次）、唯一性/一致性按组代表声明
（组内最小 statement_id）；detail_json 存全组/取值与算法版本；扫描写审计
action=evidence.quality_scan。

## v0.8.1 维护记录（2026-09-16，限流伪造头修复 + 文档时效同步，零功能变更）

范围：修复限流中间件无条件信任 X-Forwarded-For 的安全缺口（直连部署时限流可被
任意绕过），文档状态同步至 v0.8。基线 v0.8：242 passed / 94.8%。

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests --cov -q -n auto --dist loadfile` | **244 passed / 94.8%**（+2：伪造头不绕过、trust 模式桶隔离） |
| ruff / format / mypy / secret_scan / module_graph（CI 同命令） | 全部通过 |

### 缺口与修复

- **缺口**：`RateLimitMiddleware._client_key` 无条件优先取 X-Forwarded-For 归桶；
  uvicorn 直接暴露（README 默认部署）时，攻击者逐请求伪造该头即可获得无限新桶，
  限流对登录爆破与导入滥用完全失效；
- **修复**：默认只用 socket 对端 IP；`CG_TRUST_PROXY=true`（可信反向代理之后）才采信
  XFF。THREAT_MODEL 补 T10 条目；USER_GUIDE 补部署提示。

## v0.8.2 维护记录（2026-09-16，SQLite WAL + 迁移漂移检测，零功能变更）

范围：SQLite 引擎开启 WAL 与 busy_timeout；CI 接入 alembic check（ORM 与迁移 schema
漂移护栏）。基线 v0.8.1：244 passed / 94.8%。

| 命令 | 结果 |
| --- | --- |
| `uv run alembic upgrade head && uv run alembic check` | **No new upgrade operations detected**（当前零漂移；此后改 ORM 忘建迁移时 CI 在此失败） |
| `uv run pytest tests --cov -q -n auto --dist loadfile` | **245 passed / 94.8%**（+1：WAL 持久性断言） |
| ruff / format / mypy / secret_scan / module_graph（CI 同命令） | 全部通过 |

### 变更说明

- **WAL**：make_engine 的 SQLite 连接钩子设置 `PRAGMA journal_mode=WAL`（读写不互斥，
  并发读不再锁库；库文件持久属性，旧库首次连接后自动转换）与 `PRAGMA busy_timeout=5000`
  （写竞争等待而非立即报错）。测试经独立连接验证 WAL 已持久化；
- **迁移漂移检测**：CI 迁移检查步骤在 upgrade 后增加 `alembic check`，
  autogenerate 比对 ORM 元数据与当前 schema。

## v0.8.3 维护记录（2026-09-16，前端覆盖率量化 + 数据层测试 + 工作区清理，零功能变更）

范围：首次量化前端覆盖率并补数据层测试；清理 data/ 历轮运行残留；键盘焦点可见样式。
基线 v0.8.2：后端 245 passed / 94.8%，前端 61，E2E 22。

| 命令 | 结果 |
| --- | --- |
| `npx vitest run --coverage`（新增 @vitest/coverage-v8） | 总体语句覆盖 **55.9% → 59.9%**；vitest 61→**66 passed**（+5 API 层） |
| `uv run pytest tests -n auto --dist loadfile` | 245 passed 零回归 |
| `CG_API_PROXY=… npx playwright test` | **22 passed** |
| npm run build / lint / ruff / mypy | 全部通过 |

### 前端覆盖率基线（首测）

- api.ts（全站数据层）1.96% → **21.6%**：mock 全局 fetch 覆盖 request 主体分支
  （鉴权头注入、401 清 token、detail 错误提取、非 JSON 回退默认消息、token 存取）；
- 剩余未覆盖为各端点方法的模板化薄包装（逻辑核心 request 已测）与 EChart canvas
  组件（渲染归 E2E 覆盖）——按性价比止步于此；
- 纯函数模块维持高位（report 91%、eventsDisplay/riskDisplay 100% 等）。

### 工作区卫生

删除 data/ 下历轮运行残留：uvicorn 日志 ×13、pytest 输出 ×7、alembic-check/、
pytest-tmp/、dbg2.sqlite3（调试库）。保留主库、E2E 库（e2e-v05）、CSV 模板与
uv 导出的 requirements.txt。

### 可访问性

新增 `:focus-visible` 全局焦点圈（键盘 Tab 导航可见、鼠标点击不显示）。

## v0.8.4 维护记录（2026-09-16，运行时路径审计 + 鉴权层测试，零功能变更）

范围：审计两个从未细看的运行时路径（结论均干净）；鉴权层补组件测试。
基线 v0.8.3：后端 245，前端 66，E2E 22。

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests -n auto --dist loadfile` | 245 passed 零回归 |
| `cd apps/web && npm run lint && npx vitest run --coverage` | 0 errors / **74 passed**（+8 鉴权层）；总体覆盖 59.9%→**62.25%**，auth.tsx 30%→**100%** |
| `npm run build` | 通过 |

### 运行时路径审计结论（无需改动）

- **AuditMiddleware**：仅对写方法（POST/PUT/DELETE/PATCH）准备审计主体（解码 JWT
  写入 request state），GET 直通；实际落库由路由层显式调用——不是每请求写库；
- **events 实体名映射**：单条 `IN` 批量查询，无 N+1（与 evidence_for_statements
  此前结论一致）。

### 鉴权层测试（+8，auth.tsx 100%）

匿名态与角色门、viewer/analyst 预置 token 恢复、坏 token 不崩溃、login 成功写
token 与状态、login 失败状态保持、logout 清空、Provider 外调用抛明确错误。

## v0.8.5 维护记录（2026-09-16，入口资产审计 + README 端口缺陷修复）

| 项 | 结论 |
| --- | --- |
| tests/performance/test_perf.py（v0.3 最早基线） | 健康：测的是纯函数层 penetrate/analyse（2990 边 p95），与 v0.5+ 的 HTTP 端点基线分层互补，随套件持续运行且绿 |
| 启动演示.cmd | 与当前流程一致：uv sync --frozen → 迁移 → cg-seed（幂等）→ CG_WEB_DIST 托管 dist → uvicorn 8300；dist 未构建时给出明确指引 |
| README 快速开始端口 | **缺陷修复**：写的是 5173，vite 实际监听 5273（vite.config.ts），照 README 操作会打开错误地址；已改正。其余文档（USER_GUIDE/PROJECT_GUIDE/TEST_REPORT/DELIVERY）均为 5273 无误 |

后端 245 passed 零回归（全套件含 test_perf.py 持续通过）。
