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
