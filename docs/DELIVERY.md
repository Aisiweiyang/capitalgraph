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

## v0.5 交付（2026-09-14）：资本异动与证据工作台

交付日期：2026-09-14 ｜ v0.5 在 v0.4 之上把"已经算出来的结论"与"支撑它的证据、它的历史变化"
连起来：什么时候变的（变更事件流）、两个时点之间格局怎么变的（对比）、每条结论背后是哪份证据
（证据工作台与 deep-link），并补齐 v0.4 新页面的端到端质量。

### 功能与文件位置

| 切片 | 内容 | 位置 |
| --- | --- | --- |
| A 变更事件流 | diff_events 纯函数（新增/失效/比例增减/控制权/担保/质押事件，证据引用键）、/events、/entities/{id}/events、全局异动页、实体页变更轨迹区 | `cg_capital_graph/events.py`、`cg_api/routers/events.py`、`apps/web/src/pages/Events.tsx`、`eventsDisplay.ts` |
| B 格局对比 | diff_families/compare_flows 纯函数、/families/compare、/flows/compare、系谱/流动页对比模式、对比报告 | `cg_capital_graph/compare.py`、`routers/families.py`+`flows.py`、`compareDisplay.ts`、`report.ts` |
| C 证据工作台 | evidence_coverage 纯函数、/evidence/coverage·documents·lookup、证据工作台页、全站 deep-link、报告证据引用表与行内上标 | `cg_capital_graph/evidence.py`、`routers/evidence.py`、`pages/Evidence.tsx`、`components/EvidenceTable.tsx`、`reportEvidence.ts` |
| D 质量收尾 | 8 项新 Playwright（系谱详情/风险区/回放/报告下载/异动/证据/双对比模式）、性能基线、synthetic 分批缺陷修复 | `e2e/v05-pages.spec.ts`、`tests/performance/test_v05_perf.py`、ADR-018 |

### 实际测试证据（本机实测，详见 TEST_REPORT.md §v0.5）

- 后端 `pytest --cov`：**179 passed / 92.3%**（v0.4 基线 129/91.3%，零回归）
- 前端 `vitest`：**42 passed**（v0.4 基线 24，零回归）；`tsc -b && npm run build` 通过
- E2E `playwright test`：**16 passed**（基线 8 项 + 新增 8 项，零回归）
- ruff / module_graph / secret_scan / bandit：全部通过
- 性能基线：2008 声明规模下 /events p50 32.5ms、/families/compare p50 58.2ms、/flows/compare p50 74.3ms

### 顺带修复（确定性不变）

1. **synthetic 分批缺陷**：实体 > 400 时跨批声明主体键解析失败、证据静默丢失；改为
   "先全部实体批次、后全部声明批次"，并把证据缺文档从静默降级改为显式 issue（ADR-018）。
   种子载荷与顺序不变，seed=42 既有断言零回归。
2. **系族对比口径增强**：diff_families 增加成员级"被控路径归属变化"检测（控制权族内移动
   必报 changed），使 2022-06-01 持股转移在同族场景下也能被对比视图呈现。

### 已知限制

见 TEST_REPORT.md §v0.5 已知限制（事件不含 recorded_at 中间粒度、同键多声明归因退化、
超大规模需数据库侧 diff、覆盖率不评估证据内容质量、报告证据表上限 200 条）。

## v0.5.1 优化交付（2026-09-14）：性能与体验（后端零改动）

| 优化 | 效果 |
| --- | --- |
| 路由级代码分割（React.lazy + Suspense + vendor chunk 命名） | 首屏 JS 1,901.85KB（gzip 627.19KB）→ **175.88KB（gzip 58.08KB，−90.7%）**；echarts/cytoscape 按页懒加载 |
| 报告证据收集分批 | lookup 每批 200 条、总上限 1000 条；任一批失败降级为无证据表 |
| 异动页服务端筛选 + 分页 | event_type 下推服务端；"加载更多"页大小 100 |
| 变更轨迹窗口可调 | from/to 写入 URL（events_from/events_to）支持深链；空窗显式空态 |

实测：vitest 42→50 项、E2E 16 项全绿（含 1 项选择器收窄，见 TEST_REPORT §v0.5.1）、
后端复跑 179 passed / 92.3%。详见 TEST_REPORT §v0.5.1。

## v0.6 交付（2026-09-15）：证据质量治理层——覆盖率趋势与时效提示

在证据工作台（v0.5 横切面）之上补"趋势"与"新鲜度"两个维度，全部只读呈现/提示性标注，
不产生认定（ADR-019/020）：

| 切片 | 内容 | 交付 |
| --- | --- | --- |
| A 覆盖率趋势 | coverage_timeline 纯函数 + GET /evidence/coverage/timeline + 证据工作台趋势区（ECharts 柱线图 + 逐年表） | 完成 |
| B 证据时效 | EvidenceRecord.captured_at 数据链路（snapshot.fetched_at 落库、入库时间兜底）+ stale_evidence 纯函数 + GET /staleness 与 POST /staleness/scan（幂等登记复核通道，analyst+）+ 证据工作台时效区 | 完成 |
| C 报告时效标注 | 报告证据表增"快照时间"列与陈旧标注（与工作台同参数）+ 覆盖率摘要行；获取失败降级省略 | 完成 |
| D 端到端 | E2E 3 新用例（趋势区/时效区空态与列表/viewer RBAC 提示）+ 性能基线（2008 声明） | 完成 |

实测：后端 179→**203 passed / 92.7%**，前端 vitest 50→**60 passed**，E2E 16→**19 passed**，
性能基线 timeline p50 15.9ms / staleness p50 20.7ms（2008 声明）。详见 TEST_REPORT §v0.6。

### 开源调研结论

Great Expectations（Apache-2.0）/ Soda Core（Apache-2.0）/ Deequ（Apache-2.0，Spark 绑定）
的 freshness/覆盖率检查与本项目两条规则同族——**均不引入**（执行引擎与配置体系依赖过重，
纯函数路线零新增运行时依赖），规则语义借鉴并在 ADR-020 口径说明注明（详见
OSS_EVALUATION v0.6 增量，2026-09-15 版本核实）。

### 已知限制

见 TEST_REPORT.md §v0.6 已知限制（时效只提示不认定、旧库 fetched_at 语义兼容、
趋势差值不构成认定、报告降级省略、E2E 后端限流建议）。

## v0.6.1 维护交付（2026-09-16）：依赖安全升级与仓库整理

- 前端：echarts 6.1（XSS 公告）、react-router-dom 7.18（开放重定向等 2 项公告），
  npm audit 归零；jsdom 30 / jest-dom 7 开发依赖跟进。既有 60 项 vitest、19 项 E2E
  零改动通过。
- 后端：锁文件小版本升级，pip-audit 无已知漏洞；/coverage 响应附带 timeline，
  证据工作台挂载请求 4→3（独立端点保留，一致性有测试）。
- 仓库整理：开发过程性档案（docs/prompts）移出仓库，文档中的过程性指涉改为中性
  表述；交付文档只保留产品与技术内容。

实测：后端 204 passed / 92.7%，vitest 60，E2E 19，npm audit / pip-audit / bandit
级别扫描全部通过。详见 TEST_REPORT §v0.6.1。

## v0.6.2 维护交付（2026-09-16）：lint 工程拉活 + CI 现代化 + 测试补强

- 前端 ESLint 自 flat config 起真正可运行（此前 lint 脚本引用未安装的依赖），CI
  frontend job 接入；现存告警均为已确认的模式性提示（挂载取数、组件文件导出常量）。
- CI actions 全部升级到当前主版本（checkout v7 / setup-node v7 / setup-uv v10），
  清除 Node 20 弃用告警；npm audit 在依赖清零后移除永真兜底，high+ 出现即失败。
- 补齐覆盖率最低两块的单元测试（实体解析打分边界 8 项、种子幂等 2 项），并修复
  seed 模块显式参数被环境变量静默压制的缺陷。后端 214 passed / **94.1%**
  （92.7% → 94.1%），vitest 60，E2E 19，静态检查全过。详见 TEST_REPORT §v0.6.2。

## v0.6.3 维护交付（2026-09-16）：响应压缩

- API 与前端静态托管启用 gzip（阈值 1024B，避免小响应负收益）：异动页载荷
  48.7KB→8.3KB（5.9×），大 JSON 与构建产物传输体积显著下降；
- 新增压缩与阈值行为断言 2 项；vite 8.3.0 跟进；核验确认索引与批量查询无缺口气。
- 后端 216 passed / 94.3%，vitest 60，E2E 19，静态检查全过。详见 TEST_REPORT §v0.6.3。

## v0.7 交付（2026-09-16）：数据质量规则族

| 切片 | 内容 |
| --- | --- |
| A 有效性 | uscc 标识符 GB 32100-2015 校验位核查（复用 domain 层实现），非法者列为候选 |
| B 唯一性 | 同键并行 active 声明 > 1 → 疑似重复录入组（superseded 历史不进规则） |
| C 跨源一致性 | 多连接器比例冲突候选；缺失显式不可比；多源一致不算冲突 |
| D 总览与看板 | GET /evidence/quality 五维度计数与候选 + 工作台质量总览区（一键反查）+ E2E + 性能基线 |

口径（ADR-021）：三规则沿用"只提示、不认定"，互不隐含、候选互不排除；
登记复核继续复用 v0.5 QualityIssue 机制，不新增表、不新增写通道。
实测：后端 216→**228 passed / 94.4%**，E2E 19→**20 passed**，
/evidence/quality p50 53.4ms（2008 声明）。详见 TEST_REPORT §v0.7。

## v0.7.1 维护交付（2026-09-16）：可视化与流动感（前端零依赖）

- 流动感：面板进场/悬停动效、路由加载脉冲、穿透图节点滑入布局、流向线拖尾特效
  （统一流速，保留后台标签与导出可见性两条既有约束）；
- 可视化：覆盖率趋势线平滑+面积渐变；
- 无障碍：全局响应 prefers-reduced-motion，减弱动效偏好下退化为瞬时；
- 零新依赖、零功能变更，构建体积不变；vitest 60 / E2E 20 全绿。详见 TEST_REPORT §v0.7.1。

## v0.7.2 维护交付（2026-09-16）：测试套件提速 37% + lifespan 现代化

- 性能基线三用例共享会话级建库夹具（同源数据只建一次）；argon2 成本经环境变量可配
  （默认不变，测试降档）；套件 171s → **108s**（−37%，含覆盖率插桩）；
- FastAPI `on_event` 迁移 lifespan，自身代码弃用告警清零；
- 零功能变更：后端 228 passed / 94.4%，E2E 20 全绿。详见 TEST_REPORT §v0.7.2。

## v0.7.3 维护交付（2026-09-16）：mypy 全仓拉零 + CI 接入

- mypy（dev 依赖中原为摆设）全仓跑通：修复 12 处类型问题后 55 文件零错误，
  CI backend job 新增 mypy 步骤强制不回退；
- 揪出并修复潜伏仓储缺陷 user_count（await 优先级错误，调用必炸，因无调用方未暴露）；
- 前端证据工作台修复阈值切换的取数竞态（AbortController）；
- 后端 228→**233 passed / 94.5%**，vitest 60，E2E 20 全绿。详见 TEST_REPORT §v0.7.3。

## v0.7.4 维护交付（2026-09-16）：测试并行化（2×）+ 防御分支补测

- pytest-xdist（`-n auto --dist loadfile`）接入本地与 CI：含覆盖率插桩
  108s → **55s**；237 passed / 94.7%；
- db.py / normalization.py 防御性分支补测至 100%。详见 TEST_REPORT §v0.7.4。

## v0.7.5 维护交付（2026-09-16）：写通道端到端 + CI 缓存

- E2E 20→**21 passed**：补 analyst"扫描入库"写通道用例（按钮 RBAC 显隐 + 幂等登记
  created→skipped 端到端，断言与库状态无关可重复执行）；
- CI frontend job 开启 npm 缓存；registry 运维开关/regions 代码校验补测，
  后端 237→**239 passed / 94.8%**。详见 TEST_REPORT §v0.7.5。

## v0.8 交付（2026-09-16）：质量登记闭环

POST /evidence/quality/scan（analyst+）把有效性/唯一性/跨源一致性候选幂等登记进
复核通道（rule_name 按维度、实体级/组代表两级幂等键、写审计），工作台质量总览区
提供"登记复核"入口（viewer 见角色提示）。ADR-021 修订同步。
实测：后端 **242 passed / 94.8%**，vitest **61**，E2E **22** 全绿。详见 TEST_REPORT §v0.8。

## v0.8.1 维护交付（2026-09-16）：限流伪造头修复

- 限流默认不再信任 X-Forwarded-For（可被逐请求伪造而绕过限流）；反向代理部署经
  `CG_TRUST_PROXY=true` 显式开启。THREAT_MODEL 新增 T10；
- 测试 +2（默认伪造不绕过 / trust 模式桶隔离），后端 242→**244 passed**。

## v0.8.3 维护交付（2026-09-16）：前端覆盖率基线 + 工作区清理

- 首次量化前端覆盖率（@vitest/coverage-v8）：总体 55.9%→**59.9%**；数据层 api.ts
  补 5 项分支测试（鉴权头/401 清 token/错误提取/回退消息）；
- 清理 data/ 历轮运行残留（日志/临时输出/调试库）；
- 全局 :focus-visible 键盘焦点样式；
- 后端 245 不变，前端 61→**66**，E2E 22 全绿。详见 TEST_REPORT §v0.8.3。

## v0.8.4 维护交付（2026-09-16）：运行时路径审计 + 鉴权层测试

- 审计中间件与 events 实体名映射两条路径核验干净（写方法才准备审计、批量 IN
  无 N+1）；
- 鉴权层补 8 项组件测试（登录/登出/角色门/坏 token），auth.tsx 覆盖至 100%，
  前端总体 62.25%，vitest **74 passed**。详见 TEST_REPORT §v0.8.4。

## v0.8.5 维护交付（2026-09-16）：入口资产审计

- 审计最早的纯函数性能基线与启动演示脚本：均健康，无需改动；
- 修复 README 快速开始的前端端口笔误（5173 → 实际 5273）。详见 TEST_REPORT §v0.8.5。

## v0.9 交付（2026-09-17）：真实数据接入原型（阶段一）

CSV 连接器新增 `evidence_title` / `evidence_date` 可选列（ADR-022）：公告标题归档为
独立来源文档（证据链可回溯真实公告 URL），公告发布日期接证据快照 captured_at
（时效规则吃真实披露日期）。巨潮风格样例数据集（含故意脏数据）端到端验证：
质量/时效规则在真实形态数据上如预期联动。全部可选、向后兼容，synthetic 行为零变化。
实测：后端 245→**249 passed**，前端 74、E2E 22 全绿。详见 TEST_REPORT §v0.9。

## v0.9.1 维护交付（2026-09-18）：可视化表达优化

- 流向线悬停显示省对金额/笔数并加粗强调；质量五计数卡语义色（0 绿 / 候选暖色）；
  覆盖率趋势表格内嵌渐变数据条；
- 零依赖、零功能变更：后端 249 passed 不变，前端 74、E2E 22 全绿。详见 TEST_REPORT §v0.9.1。
