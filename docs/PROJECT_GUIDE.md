# CapitalGraph 项目完整指南

> 一份文档讲清四件事：这个项目是什么、代码怎么组织与开发、你自己怎么使用、出了问题怎么调试。
> 各主题的深度文档见文末"文档地图"；本文是入口与总览。更新于 v0.11（2026-09-18）。

---

## 1. 项目是什么

**CapitalGraph** 是面向中国企业研究的资本关系平台：把"谁持股谁、谁控制谁、谁担保谁、
钱往哪里流、什么时候变的、证据在哪"整成一条可核查的链路。

三个立场贯穿全部功能：

1. **证据优先**：每条结论（穿透路径、UBO 候选、系族归属）都挂证据链
   `document → snapshot(sha256) → fragment`，原始层只追加，时点查询不改写历史；
2. **只提示、不认定**：所有分析结果标注"算法候选/研究用途"并随响应附口径说明
   （algorithm_version + assumptions），不构成法律、信用或投资结论；
3. **纯函数计算**：全部算法（穿透、系族、事件、对比、质量规则）是无 IO 的纯函数，
   数据库只做输入输出投影——可测试、可复现、无隐藏状态。

当前状态（v0.11）：后端 259 项测试 / 94.9% 覆盖率，前端 78 项 vitest + 24 项 E2E，
npm/pip 审计零公告，CI 常绿。

**技术栈**：Python 3.12 · FastAPI · SQLAlchemy(async) · SQLite（生产可换 PostgreSQL）·
Alembic · argon2id + JWT；React 18 · TypeScript · Vite · ECharts（地图/图表）·
Cytoscape（关系图）。uv workspace 单仓多包，前端零运行时新增依赖策略。

---

## 2. 功能全景（按版本演进）

| 版本 | 能力 | 在哪看 |
| --- | --- | --- |
| v0.1–0.2 | 鉴权与三级 RBAC、实体/声明/证据链、时点查询、审计日志、限流、安全头 | 全站基础 |
| v0.3 | 省际资本流动：流向地图（choropleth+流向线）、省份→行业桑基、区域排名、HHI/环路等流动性指标、金额/笔数口径切换 | 资本流动页 |
| v0.4 | 系族识别（控制人聚类、交叉持股环并族）、担保链/互保圈/质押风险传导、流动页按年回放、三页一键导出自包含 HTML 研究报告 | 资本系谱页、实体页风险区 |
| v0.5 | 变更事件流（两时点声明对比）、系族/区域双时点对比模式、证据工作台、全站证据 deep-link、报告证据引用表 | 异动页、证据页 |
| v0.6 | 证据覆盖率统计 + 年度趋势、证据时效候选（1–30 年阈值）、报告快照时间列与陈旧标注 | 证据页趋势/时效区 |
| v0.7 | 质量规则族：有效性（uscc 校验位）/唯一性（重复录入）/跨源一致性（比例冲突），五维度质量总览一处呈现 | 证据页质量总览区 |
| v0.8 | 质量登记闭环：三类候选一键幂等登记复核通道（analyst），时效规则登记早已可用 | 证据页质量总览区"登记复核" |
| v0.9 | 真实数据接入原型：CSV 公告标题/公告日期列，证据链按公告归档可回溯真实 URL，时效按真实披露日期 | data/sample/真实公告风格示例.csv |
| v0.10 | 交叉验证：股东比例合计（>100% 数学矛盾）+ 导入身份冲突校验，质量六维度 | 证据页质量总览第六卡 |
| v0.11 | 中文相关度检索：命中集合不变、展示顺序按相关度评分（完全/前缀/包含/2-gram 分层） | 检索页 score 排序 |

口径要点（细节见 docs/DECISIONS.md 的 21 条 ADR）：

- 覆盖率 = 有证据片段的时点有效声明占比，缺失只呈现不修复；
- 时效 = 证据快照最近取证早于"时点 − N 年"（默认 5 年），恰好等于不算陈旧；
- 有效性只核查 uscc 命名空间（GB 32100-2015 校验位），其他命名空间不核查不计数；
- 一致性只比较双方比例都给出的情形，缺失即不可比；多源一致是多源印证不算冲突。

---

## 3. 代码结构与开发

### 3.1 仓库布局

```
packages/domain             领域模型 + ORM + 仓储 + 迁移源（cg-domain）
packages/capital_graph      穿透/系族/事件/对比/质量等算法纯函数（cg-capital-graph）
packages/entity_resolution  实体解析与打分（cg-entity-resolution）
packages/connectors         连接器 SDK + 合成数据 + CSV 导入（cg-connectors）
apps/api                    FastAPI 服务：路由/鉴权/限流/审计（cg-api）
apps/web                    React 前端（React 18 + Vite + ECharts + Cytoscape）
workers                     幂等采集 worker
migrations                  Alembic 迁移
tests                       单元 / API 集成 / 安全 / 性能（performance 标记）
scripts                     module_graph（依赖边界）/ secret_scan / sbom 等
data/                       SQLite 库与 CSV 模板（git 忽略）
```

### 3.2 分层纪律（改代码前必读）

- **依赖方向**：`domain ← capital_graph ← api`，`domain ← connectors`。
  repo 行类型定义在 domain，算法纯函数在 capital_graph，路由做两者适配——
  反向依赖会被 `scripts/module_graph.py` 拦下（CI 强制）；
- **原始层只追加**：声明用 status（active/superseded）+ valid_from/valid_to 表达时态，
  不 UPDATE 历史；新事实 = 新声明 + 旧声明 supersede；
- **算法零 IO**：算法模块不 import 数据库；输入是行投影（dataclass），输出是排序确定的
  dict——每个算法带版本常量与 assumptions，随 API 响应输出；
- **派生不落库**：事件、对比、覆盖率、质量候选都是查询时计算的只读视图。

### 3.3 常见改动走哪条路

**新增只读分析端点**（以质量规则为例）：
1. `cg_capital_graph/xxx.py`：纯函数 + `XXX_VERSION` + `XXX_ASSUMPTIONS`，
   输入行 dataclass 冻结、输出全排序；
2. `cg_domain/repo/*.py`：行类型 dataclass + 查询方法（时点过滤口径与既有端点一致）；
3. `cg_api/routers/*.py`：viewer 只读 / analyst 写入分开，响应附 at/version/assumptions；
4. `apps/web/src/api.ts`：响应类型 + request 方法 → 页面组件 + testid；
5. 测试：纯函数单测（`tests/capital_graph/`）+ API 集成（`tests/api/`，含 401/RBAC）+
   大规模性能基线（`tests/performance/`，共享 conftest 建库夹具）。

**新增前端页面**：`App.tsx` 加 `lazy` 路由（自动获得代码分割与 Suspense 反馈），
页面交互元素加 `data-testid`（E2E 依赖）。

**改算法口径**：先在 docs/DECISIONS.md 落 ADR，版本常量升位，既有确定性断言逐条过。

### 3.4 开发自测命令（按需取用）

```bash
uv run pytest tests -q -W ignore                 # 后端全量（~108s；性能共享建库）
uv run pytest tests/api/test_evidence_api.py -q  # 单文件
uv run pytest tests -k "quality" -q              # 按关键字
cd apps/web
npx tsc -b && npm run lint && npx vitest run     # 类型 / 规范 / 单测（60 项）
npm run build                                    # 产物构建
CG_API_PROXY=http://127.0.0.1:8301 npx playwright test   # E2E 20 项（需 8301 后端）
uv run ruff check packages apps workers tests && uv run ruff format --check packages apps workers tests
uv run python scripts/module_graph.py            # 依赖边界
uv run python scripts/secret_scan.py             # 密钥扫描
```

环境变量速查：`CG_DATABASE_URL`（默认 sqlite 主库）、`CG_SECRET_KEY`（生产必配）、
`CG_RATE_LIMIT_PER_MINUTE`（默认 120；本地跑 E2E 建议 1200，否则并发用例会触发 429
假失败）、`CG_ARGON2_*`（口令哈希成本，测试降档用）、`CG_API_PROXY`（前端代理目标端口）、
`CG_ENV=test`、`CG_WEB_DIST`（前端托管目录）。

### 3.5 提交与 CI

- 提交信息惯例：`feat:/fix:/perf:/chore: 主题——要点`，正文用短横线列条目，不写尾注；
- 一次交付一个提交，推送后到 Actions 确认 CI 绿（backend：ruff/边界/测试/秘密扫描/
  bandit/迁移回环；frontend：lint/build/test/audit）；
- 本机网络若阻断 github.com:443，用钉定边缘 IP 推送：
  `git -c http.curloptResolve="github.com:443:140.82.112.3" push origin main`
  （被 reset 就换 140.82.113.3 / 20.200.245.247 或多试几次）。

---

## 4. 个人使用手册

### 4.1 启动

**最快**：双击仓库根目录 `启动演示.cmd`（安装→迁移→种子→启动），浏览器开
`http://127.0.0.1:8300`。

**手动 / 开发模式**：

```bash
uv sync && uv run alembic upgrade head && uv run cg-seed --entities 40
uv run uvicorn cg_api.main:app --port 8300          # 后端 + 托管前端
# 或前后端分离开发：
cd apps/web && npm install && npm run dev           # http://localhost:5273，/api 自动代理
```

演示账号（种子创建，仅限本地）：`admin` / `analyst` / `viewer`，口令均为
`<角色>-demo-password`。viewer 只读；analyst 可执行"扫描入库"等写操作；admin 另有
管理端与审计日志。生产部署必须换口令并配置 `CG_SECRET_KEY`。

### 4.2 推荐演示路径

1. **检索 → 穿透**：首页检索"有限公司"→ 打开企业 →「在穿透图中查看」→ 切方向/时点 →
   双击节点展开；左侧栏每条结论带「查看」证据链接；
2. **证据链**：任意结论点「证据」→ 跳证据工作台反查，看 document→snapshot(sha256)→fragment
   三层与内容哈希；
3. **流动地图**：资本流动页切金额/笔数口径、拖年回放、看桑基与 HHI 卡片；
4. **异动与对比**：异动页窗口选 2022-01-01→2023-01-01（合成数据的持股转移窗口）→
   点事件 deep-link；系谱/流动页开"对比模式"并导出对比报告；
5. **质量治理**：证据页从上到下——覆盖率卡片（当前 100%）→ 年度趋势图 → 质量总览
   五计数 → 时效风险区（阈值调 30 看空态、调回 5 看质押候选）→ 候选行「反查」；
6. **报告导出**：穿透/系谱/流动页「导出报告」→ 自包含 HTML（图表内联、证据引用表、
   口径版本、免责声明），浏览器双击即开。

### 4.3 导入自己的数据

CSV 连接器支持自备数据：模板在 `data/sample/`，`record_type` 列区分
`entity`（主体）/ `holding`（持股）/ `control`（控制），支持省份/行业/金额列。
通过管理端或 `/api/v1/ingest/runs`（connector: csv）导入；合成连接器
（connector: synthetic）用 `--entities/--seed` 控制规模与确定性，适合演示与压测。

---

## 5. 调试指南

### 5.1 出了问题先看这三处

1. **健康检查**：`curl http://127.0.0.1:8300/api/v1/health` —— `database: ok` 说明库通；
   `degraded` 看 CG_DATABASE_URL 指向的库文件是否存在/迁移是否到 head；
2. **接口层**：`http://127.0.0.1:8300/api/v1/docs` 打开 OpenAPI UI，直接重放请求看
   状态码与响应体（401=未带 token、403=角色不够、422=参数越界、429=限流）；
3. **日志**：uvicorn 终端输出含审计与未捕获异常（500 不向客户端泄露堆栈，细节在日志）；
   admin 登录后管理端可查审计日志（谁在何时做了什么写操作）。

### 5.2 常见故障速查

| 症状 | 原因与处置 |
| --- | --- |
| 前端请求全 404/ECONNREFUSED | 后端没起或端口不一致：开发模式设 `CG_API_PROXY=http://127.0.0.1:<后端端口>` |
| 端口被占 | 启动脚本/命令换端口（后端 8300、前端 5273、E2E 惯例 8301） |
| 登录后仍 401 | JWT 密钥变化或 token 过期：退出重登；生产换 CG_SECRET_KEY 后所有旧 token 失效 |
| E2E 大面积 429 失败 | 后端默认限流 120/分被并发用例打满：用 `CG_RATE_LIMIT_PER_MINUTE=1200` 起 E2E 后端 |
| 请求响应"过于频繁" | 同上，限流中间件正常工作；等 1 分钟或调额度 |
| 页面空白/数据缺失 | 打开开发者工具网络面板看具体接口；库为空则重新 `cg-seed` |
| 重置演示数据 | 停服务 → 删 `data/capitalgraph.sqlite3` → `alembic upgrade head` + `cg-seed` |
| 测试因端口/库互相干扰 | pytest 与 E2E 用独立库文件；`CG_DATABASE_URL` 别指向主库 |

### 5.3 数据库直查（SQLite）

```bash
uv run python -c "import sqlite3;print(sqlite3.connect('data/capitalgraph.sqlite3')\
.execute('select predicate,count(*) from relationship_statements group by 1').fetchall())"
```

常用表：`entities`（主体）、`relationship_statements`（声明，时态左闭右开）、
`entity_identifiers`（标识符，uscc 等命名空间）、`source_documents/source_snapshots/
evidence_fragments`（证据三层）、`quality_issues`（复核通道）、`audit_logs`（审计）。

### 5.4 确定性与复现

- 合成数据由 `--seed` 完全确定：`seed=42` 是测试基线（含 2022-06-01 持股转移、
  质押证据取证时间 2019-01-01 等已知事实，测试断言依赖它们）；`seed=40` 是 E2E 库；
- 生成器有不变量自检（如产出的 USCC 必须通过校验位，否则直接抛错）——
  看到 `synthetic generator produced invalid USCC` 说明生成逻辑被改坏；
- 前端图表刻意关闭了入场动画（流向线）：后台标签页 rAF 节流会让动画停在 0% 导致
  整线不可见，导出 PNG 需要确定性渲染——拖尾特效叠加在静态线之上，不受影响。

### 5.5 测试与前端调试

- 后端：`pytest -k <关键字>` 缩小范围；`--durations=12` 找慢测试；`-s` 看性能基线
  print 输出；性能用例共享建库夹具（tests/performance/conftest.py）；
- E2E：失败后看 `apps/web/test-results/` 下的 trace（`npx playwright show-trace <zip>`），
  回放每一步截图与网络；
- 前端：vite dev 热更新即时生效；EChart/GraphCanvas 在 window 上暴露
  `__echarts_instances` 供控制台检查实例状态。

---

## 6. 文档地图

| 文档 | 内容 | 什么时候读 |
| --- | --- | --- |
| README.md | 项目门面：快速开始、功能亮点 | 第一次接触 |
| 本文 PROJECT_GUIDE.md | 全景入口：开发/使用/调试 | 每次接手或答疑 |
| docs/ARCHITECTURE.md | 分层、模块职责、各版本架构增量、请求链路 | 改架构或加模块前 |
| docs/DATA_MODEL.md | 数据模型、时态规则、各版本视图口径 | 动数据层前 |
| docs/DECISIONS.md | ADR-001~021：每个口径与取舍的"为什么" | 对任何口径有疑问时 |
| docs/USER_GUIDE.md | 页面操作细节、CSV 导入、常见自定义 | 日常使用 |
| docs/PROJECT_STATUS_AND_DEBUG_GUIDE.md | 已知坑位与续跑方法 | 调试卡住时 |
| docs/TEST_REPORT.md / DELIVERY.md | 每轮实测命令与结果 / 交付与已知限制 | 核实"真的测过吗" |
| docs/OSS_EVALUATION.md / THIRD_PARTY_NOTICES.md / SBOM.cdx.json | 开源调研与许可 | 引入依赖前 |
| docs/PROJECT_PLAN.md | 各版本验收清单（v0.4–v0.7 全勾） | 规划下一轮 |
| docs/THREAT_MODEL.md / DATA_GOVERNANCE.md / MIGRATION.md | 威胁模型 / 合规 / 迁移 | 部署与评审 |
