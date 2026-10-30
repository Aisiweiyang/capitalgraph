# CapitalGraph 项目现状与使用调试指南

快照时间：2026-09-13 ｜ 基线版本 v0.3.1（已推送、CI 绿）｜ v0.4 开发进行中

本文是**面向使用者/开发者的实操快照**：当前做到哪了、怎么跑起来、怎么调试。
权威设计文档见 `docs/` 下的 ARCHITECTURE / DATA_MODEL / DECISIONS（ADR）/ USER_GUIDE / TEST_REPORT / DELIVERY。

---

## 1. 项目是什么

CapitalGraph 是一个**中国企业资本关系研究平台**（演示数据全部为确定性合成，不指向真实主体）：

- **时态声明模型 + 证据链**：document → snapshot(sha256) → fragment，原始层只追加，修正走 supersede；
- **三层研究能力**：
  1. 单点穿透（v0.1–0.2）：向上/向下穿透、环路、交叉持股、聚合有效权益、UBO 候选（R1/R2）；
  2. 区域资本流动（v0.3）：省际流向、HHI、环路资金、年度趋势、省→行业桑基、ECharts 中国地图；
  3. 资本系谱与风险传导（v0.4，开发中）：系族识别、担保链/互保圈传导、时间回放、报告导出；
- **合规口径**：所有风险/UBO/系族结果一律为"算法候选"，界面与 API 均标注不构成法律认定或投资建议。

技术栈：Python 3.12 + uv workspace + FastAPI + SQLAlchemy（SQLite 默认/PG 可选）｜前端 Vite + React + TS strict + Cytoscape + ECharts 5.6。

## 2. 当前状态快照

### 2.1 版本与提交

| 提交 | 内容 | 状态 |
| --- | --- | --- |
| `a375ba3` | v0.3.1 易用性（USER_GUIDE、启动演示.cmd、CSV 自备数据增强） | 已推送，CI 绿 |
| `c16f51f` | **v0.4 切片A 资本系谱**（families 纯函数 + /families API + 前端系谱页） | 本地已提交，**未推送** |
| （工作区） | **v0.4 切片B 风险传导**（部分完成） | **未提交** |

### 2.2 v0.4 四切片进度

| 切片 | 内容 | 状态 |
| --- | --- | --- |
| A 资本系谱 | 系族识别算法/API/前端页 | ✅ 完成并提交（后端 106 项 + 前端 11 项全绿） |
| B 担保/质押风险传导 | synthetic 场景、risk_chains 算法、RiskFlag、前端传导区 | 🔶 进行中（见 2.3） |
| C 时间演化回放 | 资本流动页按年回放 | ⬜ 未开始 |
| D 研究报告导出 | 自包含 HTML 快照 | ⬜ 未开始 |
| 收尾 | 全量验证、9 份文档同步、推送确认 CI | ⬜ 未开始 |

### 2.3 工作区未提交内容（切片B 已做部分）

已修改：`packages/capital_graph/.../__init__.py`（导出风险链 API）、
`packages/connectors/.../synthetic.py`（链式担保圈 C2→C3→C4→C5、环式互保圈 C5→C6→C7→C5、股权质押演示，独立 rng 不干扰既有序列）、
`packages/domain/.../enums.py`（FlagType 新增 guarantee_cycle / guarantee_chain_exposure）。
新增：`cg_capital_graph/risk_chains.py`（担保链/互保圈/风险传导纯函数）、`tests/capital_graph/test_risk_chains.py`。

**切片B 剩余工作**：repo 层 `guarantee_rows`/`list_risk_flags` 方法 → `/api/v1/risk/*` 路由（链条查询 viewer 可读、compute 写 RiskFlag 需 analyst）→ CSV 连接器 record_type 扩展 guarantee/pledge → 实体详情页「风险传导」区 + 复核页风险标记块 → 集成测试 → 文档。

### 2.4 最近一次实测证据（本次快照实测）

```
uv run pytest tests -p no:warnings        → 116 passed in 7.05s（含未提交的切片B代码）
uv run python scripts/module_graph.py     → 模块边界校验通过
前端（切片A提交时）                        → vitest 11 passed、tsc -b 通过、npm run build 通过
```

## 3. 目录结构速览

```
资本图谱/
├── 启动演示.cmd                  # 一键演示入口（Windows）
├── apps/
│   ├── api/src/cg_api/           # FastAPI：routers/{entities,penetration,flows,families,ingest,ops,stats}
│   └── web/                      # 前端：src/pages/{Dashboard,Flows,Families,Search,Entity,Explore,Review,Admin}
│       ├── e2e/                  # Playwright E2E
│       └── src/components/       # GraphCanvas(穿透图)、FamilyGraph(系族子图)、EChart
├── packages/
│   ├── domain/                   # ORM、领域模型、枚举、repo（sqlite/pg 双方言）
│   ├── capital_graph/            # 纯函数算法：engine(穿透)、analysis(聚合/UBO)、flows(流动)、families(系族)、risk_chains(风险链)
│   ├── connectors/               # synthetic(确定性合成)、csv(自备数据)、ingest 流水线
│   └── entity_resolution/        # 名称/标识符解析
├── workers/                      # 后台任务
├── scripts/                      # module_graph.py(边界CI强制)、secret_scan.py、sbom.py
├── migrations/ + alembic.ini     # 数据库迁移
├── data/                         # SQLite 库文件（capitalgraph.sqlite3 为主库）、CSV 模板在 data/sample/
└── docs/                         # 全部交付文档
```

## 4. 怎么跑起来

### 4.1 方式一：一键演示（最简单）

双击项目根目录 `启动演示.cmd`，它依次执行：依赖安装（uv sync）→ 迁移（alembic）→ 演示数据（cg-seed，已有数据自动跳过）→ 启动服务。
完成后访问 **http://127.0.0.1:8300**。端口被占用就把脚本里 8300 改成其他端口。

### 4.2 方式二：前后端分离开发模式

```bash
# 终端1：后端（端口 8300）
uv run alembic upgrade head
uv run cg-seed --entities 40            # 首次导入演示数据；重复执行幂等跳过
uv run uvicorn cg_api.main:app --reload --port 8300

# 终端2：前端（端口 5273，/api 自动代理到 127.0.0.1:8300）
cd apps/web
npm install
npm run dev                              # 访问 http://127.0.0.1:5273
```

- 后端端口不是 8300 时：设环境变量 `CG_API_PROXY=http://127.0.0.1:<端口>` 再启动前端。
- API 文档：http://127.0.0.1:8300/api/v1/docs （Swagger UI）。

### 4.3 演示账号（cg-seed 自动创建）

| 账号 | 密码 | 角色 | 能做什么 |
| --- | --- | --- | --- |
| admin | admin-demo-password | admin | 全部 + 用户管理 + 审计日志 |
| analyst | analyst-demo-password | analyst | viewer + 运行采集、复核处理 |
| viewer | viewer-demo-password | viewer | 只读：检索/穿透/流动/系谱等 |

未登录只能看登录页；多数查询接口要求 viewer 及以上（401 = 未登录，403 = 角色不足）。

### 4.4 页面导览（登录后）

| 路由 | 页面 | 说明 |
| --- | --- | --- |
| `/dashboard` | 总览 | 实体/声明统计、采集运行状态（纯 SVG 图） |
| `/flows` | 资本流动 | 省际地图 choropleth、流向线、HHI、桑基、年度趋势、省份下钻 |
| `/families` | 资本系谱（v0.4 新增） | 系族列表（规模/省份/环路排序、阈值可调）→ 族详情（Cytoscape 子图 + 被控路径 + 族间流向表） |
| `/` | 检索 | 按名称/信用代码/证券代码找主体 |
| `/explore/:id` | 穿透图 | 方向/时间点/层级/最小比例可调；UBO 候选、股东聚合、环路、交叉持股；导出 PNG/CSV |
| `/entities/:id` | 实体详情 | 别名、标识符、股东/投资声明、证据片段下钻 |
| `/review` | 复核（analyst+） | 复核队列、质量问题 |
| `/admin` | 管理（admin） | 用户创建、采集连接器运行 |

### 4.5 数据管理

- **演示数据**：`uv run cg-seed --entities 40`（参数 seed 默认 42，同 seed 必然同数据）。
- **重置数据库**：停止服务后删除 `data/capitalgraph.sqlite3`（及不需要的 `data/*.sqlite3`），重新 `alembic upgrade head` + `cg-seed`。
- **自备 CSV**：模板见 `data/sample/`，在管理页或 API 以 `csv` 连接器导入（path 参数指向文件）。
- 数据库连接：默认 `sqlite+aiosqlite:///./data/capitalgraph.sqlite3`，可用环境变量 `CG_DATABASE_URL` 覆盖（PG 用 `postgresql+asyncpg://...`，见 MIGRATION.md）。

## 5. API 速览（均挂 `/api/v1`，除 health/login 外需 Bearer Token）

| 分组 | 端点 | 说明 |
| --- | --- | --- |
| 系统 | `GET /health` | 探活 + DB 连通 |
| 认证 | `POST /auth/login` | JWT（argon2id 校验） |
| 主体 | `GET /entities/search`、`/entities/{id}`、`/entities/{id}/shareholders|investments|history|evidence`、`/entities/by-region/{code}` | 检索与详情 |
| 穿透 | `GET /penetration/{id}?direction=&at=&min_ratio_percent=`、`.../export.csv` | 穿透分析（时点 at 左闭右开） |
| 流动 | `GET /flows/regions|summary|industries|timeline?at=` | 区域流动聚合（v0.3） |
| 系谱 | `GET /families?sort_by=size|regions|cycles&min_control_ratio_percent=&at=`、`GET /families/{root}`、`GET /families/flows` | 系族识别（v0.4 新增，viewer 可读） |
| 统计 | `GET /stats` | 总览仪表板数据 |
| 采集 | `GET /ingest/connectors`、`POST /ingest/runs`（analyst+） | 连接器与运行 |
| 运营 | `GET|POST /review/*`（analyst+ 写）、`GET /quality/issues`、`GET /audit`（admin） | 复核/质量/审计 |

## 6. 怎么调试

### 6.1 后端测试（pytest，当前 116 项）

```bash
uv run pytest tests -q -p no:warnings          # 全量（约 5–7 秒）
uv run pytest tests -p no:warnings             # 带进度显示
uv run pytest tests/capital_graph/test_families.py -q   # 单文件
uv run pytest tests -k "families" -x -q        # 按名过滤、遇错即停
uv run pytest tests --cov --cov-report=term    # 覆盖率（CI 同款）
```

- 测试用独立内存 SQLite（`tests/conftest.py`），不污染 `data/`；API 测试的临时库在 `data/pytest-tmp`。
- 调试时想看 SQL/日志：设 `CG_LOG_LEVEL=DEBUG` 再起 uvicorn。

### 6.2 前端测试与类型（vitest，当前 11 项）

```bash
cd apps/web
npx vitest run                       # 全量（jsdom，图表组件以 stub 替换）
npx vitest run src/Families.test.tsx # 单文件
npx vitest                           # watch 模式
npx tsc -b                           # 仅类型检查（strict）
npm run build                        # tsc + vite 构建（产物 dist/）
```

### 6.3 E2E（Playwright）

```bash
# 前置：后端已在 8300 运行且已导入演示数据
cd apps/web
npx playwright test                  # 自动拉起 vite dev(5273，已运行则复用)
```

- 登录态由 setup 项目经 API 预置（`e2e/auth.setup.ts`）。
- 失败时 trace 在 `apps/web/test-results/`，用 `npx playwright show-trace <文件>` 回放。

### 6.4 静态检查与 CI 同款命令

```bash
uv run ruff check packages apps workers tests        # lint
uv run ruff format packages apps workers tests       # 格式化（CI 要求已格式化）
uv run python scripts/module_graph.py                # 模块边界（包依赖声明 vs 实际 import）
uv run python scripts/secret_scan.py                 # 秘密扫描
uvx bandit -q -r packages apps/api/src workers/src   # SAST
```

推送前按这个顺序跑一遍，CI（GitHub Actions：后端 + 前端两个 job）就能保持绿。

### 6.5 数据库调试

- 主库文件：`data/capitalgraph.sqlite3`。快速查看：
  `uv run python -c "import sqlite3;print(sqlite3.connect('data/capitalgraph.sqlite3').execute('select predicate,count(*) from relationship_statements group by 1').fetchall())"`
- 迁移回环（CI 同款）：`uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head`（需 `CG_DATABASE_URL` 指向临时库）。
- 时态口径提醒：查询一律 `status=active` 且 `valid_from <= at < valid_to`（左闭右开），手写 SQL 验证时注意。

### 6.6 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| 接口 401 | 未登录或 token 过期 → 重新登录；前端会自动清除本地 token |
| 接口 403 | 角色不足（如 viewer 跑采集）→ 换 analyst/admin 账号 |
| 请求 429 | 触发限流中间件 → 稍等重试；演示数据导入属写操作也计数 |
| 前端页面空白/接口 CORS 报错 | 后端没在 8300 → 启动后端，或设 `CG_API_PROXY` 后重启 vite |
| 端口被占用 | 启动脚本里改 8300 → 8301；vite 端口在 `vite.config.ts`（5273） |
| 地图/图表不显示 | jsdom 测试中为预期（stub）；浏览器中检查是否登录、数据是否已导入 |
| 外链图片打不开 | CSP 限制（`img-src 'self' data:`），属安全设计 |
| `uv sync` 失败 | 先 `uv sync --frozen` 确认 lock 一致；改动依赖后需重新 lock |
| 演示数据"看起来没变化" | cg-seed 幂等跳过已有数据；要重建请先删库再导入 |

## 7. 注意事项与已知限制

1. **算法候选口径**：穿透/UBO/系族/风险传导结果均带 `algorithm_version` + `config_hash`，仅供研究，不构成法律认定或投资建议（界面页脚与 API assumptions 字段均有标注）。
2. **合成数据**：全部主体虚构（USCC 为 93 测试号段），同 seed 可复现；地图数据来自 DataV.GeoAtlas，正式出版物需换标准审图号地图。
3. **切片B 未完成**：`/api/v1/risk/*` 路由、前端传导区、CSV guarantee/pledge 支持尚未实现；当前工作区含未提交代码，`git status` 可见 5 个文件。
4. 前端 `npm run lint` 需要 eslint 可执行文件（devDependencies 未含 eslint，CI 也不跑 lint），可忽略。
5. 交叉持股环 C0↔C1 为 30%/25%，低于系族默认阈值 50%，默认不并族（口径见后续 ADR-016）。

## 8. 新会话续跑方法

接续未完成的开发轮次时：先读 `docs/PROJECT_PLAN.md`（当轮验收清单）、`docs/DECISIONS.md`
与 `docs/TEST_REPORT.md`（已实测结论），结合 `git log` / `git status` 确认工作区状态；
跑 `uv run pytest tests -q` 与 `uv run python scripts/module_graph.py` 做最小状态检查，
从验收清单第一个未完成项继续。
