# 使用与自定义指南（USER GUIDE）

面向使用者与二次开发者。读完这页你就能：启动系统、看懂每个页面、导入自己的数据、
以及知道"想改 X 应该动哪个文件、改完怎么验证"。

---

## 1. 启动

### 方式一：一键脚本（Windows，推荐）

双击仓库根目录的 **`启动演示.cmd`**。它会依次：安装依赖 → 数据库迁移 → 写入演示数据 → 启动服务。
看到 `Uvicorn running on http://127.0.0.1:8300` 即成功，浏览器打开该地址即可。

> 首次使用需先构建一次前端：`cd apps/web && npm install && npm run build`。
> 端口被其他项目占用时，把脚本里 `--port 8300` 改成别的（如 8301）。

### 方式二：手动命令（开发模式，前后端热更新）

```bash
# 后端（默认 SQLite，零依赖）
uv sync
uv run alembic upgrade head
uv run cg-seed --entities 40          # 演示数据；重复执行自动跳过
uv run uvicorn cg_api.main:app --port 8300

# 前端（另开终端；5273 端口，API 自动代理到 8300）
cd apps/web
npm install
npm run dev                            # CG_API_PROXY=http://127.0.0.1:8301 npm run dev 可改代理目标
```

生产形态（PostgreSQL）：`docker compose -f infra/docker-compose.yml up -d`，然后
`CG_DATABASE_URL=postgresql+asyncpg://cg:cg@localhost:5432/capitalgraph uv run alembic upgrade head`。

### 登录

| 账号 | 口令 | 能做什么 |
| --- | --- | --- |
| viewer | viewer-demo-password | 看所有页面（总览/流动/检索/穿透） |
| analyst | analyst-demo-password | + 复核队列、采集任务 |
| admin | admin-demo-password | + 管理端（建用户/审计/连接器开关） |

新用户由 admin 在「管理」页创建，或调 `POST /api/v1/admin/users`。演示口令仅限本地。

---

## 2. 页面速览

| 页面 | 用途 | 上手要点 |
| --- | --- | --- |
| **总览** `/dashboard` | 数据资产一屏掌握 | 五张卡片 + 类型/关系/年份/状态分布；卡片可点直达对应页 |
| **资本流动** `/flows` | 省际资本流动研究 | 地图红=净流出/绿=净流入；弧线=省际流向（宽度随"金额/笔数"切换）；点省份下钻看明细与主体；卡片行有 HHI 集中度与环路资金 |
| **资本系谱** `/families` | 系族识别（谁在控制一片企业） | 列表按规模/省份覆盖/环路数排序，控制阈值可调（默认 ≥50%）；点行看族详情：控制人居中的子图（成员按省份着色、控制边虚线、环上节点红框）+ 被控路径表 + 与外界的流向表 |
| **检索** `/` | 找实体 | 名称模糊 + 统一社会信用代码/证券代码精确 |
| **实体详情·风险传导** | 担保/质押风险 | 担保链条 A→B→C（名义金额，缺失显式"金额未知（缺 N 段）"）、互保圈标"环闭合"、传导模拟（假设该主体出险逐层受累）、股权质押敞口 |
| **资本流动·按年回放** | 格局随时间演化 | "播放/暂停 + 年份滑块"逐帧回放（帧=年末时点），地图着色与流向线随年变化；已取帧有缓存，退出回放回到当前 |
| **穿透图** `/explore` | 股权穿透分析 | 顶部可直接搜索主体；方向/时间点/层级/最小比例四个旋钮；红边框=环路节点、金边=UBO 候选、虚线=控制声明；双击节点以其为根重穿；PNG/CSV 导出 |
| **复核** `/review` | 数据质量人工处置 | analyst 及以上；处理冲突/疑似重复/低置信项 |
| **管理** `/admin` | 用户、审计、连接器 | admin 专属；连接器可停用 |

所有"候选"类结果（UBO、聚合权益）都附算法假设与证据链接——从穿透图侧栏点「查看」可回溯到原始证据片段。

### v0.4 新增：研究工具三件套

1. **资本系谱**（导航「资本系谱」）：自动把"同一实际控制人直接/间接控制的企业"聚成系族；
   交叉持股环上的实体会被并进同一族。列表页可调控制阈值重算；详情页可「导出报告」生成
   自包含 HTML（含子图截图、成员路径、口径与免责声明）。
2. **风险传导**（实体详情页下方）：基于担保声明计算。链条方向=义务方向（被担保方出险→
   担保方受累）；互保圈由算法登记为风险标记，analyst 可在「复核」页触发"重新计算风险标记"，
   新标记会出现在复核页「算法风险标记」区块（含输入摘要与算法版本，幂等去重）。
3. **按年回放与报告导出**（资本流动页）：回放控件在地图上方；右上角「导出报告」把当前
   视图（含回放帧年份）连同地图截图导出为单个 HTML 文件——可直接发给同事，浏览器双击即开，
   数据不出本机。

> 口径提醒：系族、风险传导、UBO 全部为**算法候选**，仅供研究参考，不构成法律认定或投资建议；
> 各报告与页面均附算法版本与配置哈希，结果可复现可追溯（ADR-016）。

---

## 3. 导入你自己的数据

### 方式一：CSV（推荐起步）

复制 `data/sample/自备数据模板.csv`，照格式填写。**列含义**：

| 列 | 必填 | 说明 |
| --- | --- | --- |
| `evidence_title` | | 来源公告/文件标题（如巨潮公告标题）。填写后证据链按公告独立归档、标题可见可跳转；示例见 `data/sample/真实公告风格示例.csv` |
| `evidence_date` | | 公告发布日期（YYYY-MM-DD）。写入证据取证时间，时效规则按此判定；非法日期该行拒绝 |
| `record_type` | ✅ | `entity`（主体）/ `holding`（持股）/ `control`（控制） |
| `subject_id/subject_name` | ✅ | 主体方；ID 以 P 开头自动识别为自然人，否则企业 |
| `subject_uscc` | 可选 | 统一社会信用代码（须过 GB 32100 校验位） |
| `region_code` | 可选 | 6 位省级行政区划代码（如 110000 北京），导入后才能上流动地图 |
| `industry` | 可选 | 行业名（建议用国标门类，如"制造业"） |
| `predicate` | — | 占位列，语义由 record_type 决定，随便填 |
| `object_*` | holding/control 必填 | 对手方（被持股企业） |
| `ratio` / `ratio_unit` | holding 必填 | 比例（percent 或 fraction）；确实未知就留空 |
| `valid_from` / `valid_to` | 可选 | 生效区间（ISO 日期，左闭右开）；留空=至今 |
| `amount_wan` | 可选 | 金额（**万元**），流动图金额口径使用 |
| `evidence_url` / `field_path` / `raw_value` | 可选 | 证据留痕，强烈建议填来源链接 |

导入（admin 登录后）：

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8300/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin-demo-password"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -X POST http://127.0.0.1:8300/api/v1/ingest/runs \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"connector":"csv","params":{"path":"data/sample/自备数据模板.csv"}}'
```

特性：**幂等**（同数据重复导入自动跳过）、**坏行隔离**（单行非法只丢该行并留痕，不中断整批）、
导入后到「资本流动」页即可看到你自己的省际流向。

### 方式二：写一个 connector（批量/在线数据）

参照 `packages/connectors/src/cg_connectors/synthetic.py` 实现 `BaseConnector`：
声明来源合规信息（`ConnectorSpec`）、产出 `EntityRecord/StatementRecord` 列表、保证幂等键。
合规红线见 `DATA_GOVERNANCE.md`（禁止绕过反爬、禁止批量导出商业数据库）。

---

## 4. 常见自定义：改哪里

| 我想改… | 动这个文件 | 改完跑 |
| --- | --- | --- |
| 演示数据规模/结构 | `uv run cg-seed --entities 200`（数量）；省份权重/金额分布在 `packages/connectors/src/cg_connectors/synthetic.py` | `uv run pytest tests/connectors` |
| 省份/行业参考列表 | `packages/domain/src/cg_domain/regions.py`（PROVINCES/INDUSTRIES） | `uv run pytest tests` |
| 流动统计口径（算哪些关系、时点、阈值） | `apps/api/src/cg_api/routers/flows.py` 的 `_FLOW_PREDICATES` 与路由参数；底层口径在 `packages/capital_graph/src/cg_capital_graph/flows.py` | `uv run pytest tests/capital_graph/test_flows.py tests/api` |
| HHI 等指标定义 | 同上 `flows.py`（函数有口径注释，对应 ADR-014） | 同上 |
| 地图配色/流向线宽度/TopN | `apps/web/src/pages/Flows.tsx`（DIVERGING_COLORS、lineWeight、slice 数量） | `cd apps/web && npm test && npm run build` |
| 实体类型颜色/图样式 | `apps/web/src/components/GraphCanvas.tsx`（KIND_COLOR 与 cytoscape style） | `npm test` |
| 数据库/端口/密钥 | 环境变量 `CG_DATABASE_URL` / `--port` / `CG_SECRET_KEY`，见 `docs/MIGRATION.md` | 重启服务 |
| 新增 API | `apps/api/src/cg_api/routers/`（参照 stats.py 最简）并在 `main.py` 注册 | `uv run pytest tests/api` |

**模块边界**：每个 Python 包只准依赖它 pyproject 里声明过的包，`uv run python scripts/module_graph.py`
会强制检查（CI 也跑）。想新增包或跨包引用，先改对应 `pyproject.toml` 的声明。

---

## 5. 改完之后：自测四件套

```bash
uv run pytest tests --cov                       # 后端行为（当前 80 项 / ~90% 覆盖）
uv run python scripts/module_graph.py           # 模块边界
cd apps/web && npm test && npm run build        # 前端
cd apps/web && npx playwright test              # E2E（需后端在代理目标端口运行）
```

全绿后正常 `git add` / `git commit` / `git push`——GitHub Actions 会再跑一遍
（lint、测试、边界、秘密扫描、bandit、迁移回环、前端构建），保持绿色即可放心迭代。

## 6. 继续开发：任务拆分建议

本项目按"一份任务一份验收"的方式演进。无论谁（人或工具）执行下一轮改动，
建议每个任务写成同一种格式：目标 → 功能范围 → 技术约束（含许可证与依赖策略）→
验收清单。完成后按惯例补齐测试证据与文档增量，验收清单逐项打勾并附实测命令。
## 7. 常见问题

| 现象 | 处理 |
| --- | --- |
| 页面空白/报"页面渲染出错" | 界面会显示错误详情（ErrorBoundary）；把截图/文本反馈给开发流程即可定位 |
| 端口 8300 被占用 | 换端口启动；开发模式再配 `CG_API_PROXY`（见 §1 方式二） |
| 地图不显示流向线 | 先切换"线宽口径"（金额需数据带 amount_wan）；合成数据与 CSV 模板均已带金额 |
| 登录 401 | 演示口令见 §1 表格；生产环境务必设置 `CG_SECRET_KEY` 并改密 |
| 地图用于出版物 | 本仓库内置 GeoJSON 仅为研究演示（来源见 `apps/web/src/assets/MAP_DATA_SOURCE.md`）；正式出版须使用自然资源部标准地图（审图号） |
| 想清空重来 | 删除 `data/capitalgraph.sqlite3` 后重跑 `启动演示.cmd`（会重建并重新种子） |

---

## 8. v0.5 新功能：异动、对比与证据工作台

### 全局异动页（/events）

选择 from/to 两个日期 → 展示该窗口内"声明层面的变更事件"时间线：持股新增/失效、
持股比例增减（带前后值与差值）、控制权获得/丧失、担保/质押新增/解除。类型筛选在
服务端执行（下拉或 chips，chips 计数为全窗口口径）；长列表用"加载更多"分页（每页 100）。
每条事件可跳转相关实体或一键打开其证据。事件由两时点有效快照对比派生，只陈述声明层面
的变化，不做动机推断（算法候选）。

### 实体页"变更轨迹"

实体详情页在风险传导区上方新增变更轨迹区（默认窗口 2022-01-01 → 2023-01-01），
列出与该实体相关的前后变化，点"证据"直接查看支撑声明。窗口可调：from/to 日期选择
会写入地址栏（events_from/events_to 参数），可直接复制带窗口的链接分享。

### 资本系谱 / 资本流动的"对比模式"

两页头部均有"对比模式"按钮：选择两个时点 →
- 系谱页：族出现/消失、族变化（成员增减、控制权在族内移动、环路数变化）差异高亮表；
- 流动页：省际流向条数、跨省金额、HHI 的 before/after/差值，以及新增/消失/变化流向对。
对比结论可一键导出对比报告（自包含 HTML）。

### 证据工作台（/evidence）

- **覆盖率卡片**：当前时点声明证据覆盖率（有证据片段的 active 声明占比），按谓词/
  连接器/年度分组；覆盖率只呈现数据现状，不修复、不推断；缺失证据的声明显式列出；
- **按声明反查**：输入一个或多个声明 ID（逗号分隔），查看其 document→snapshot(sha256)
  →fragment 证据链；
- **按来源文档浏览**：文档 → 快照 → 片段逐层展开；
- **全站 deep-link**：穿透页 UBO/股东聚合行、系谱页成员路径行、复核页风险标记、
  异动页事件中的"证据"链接都会带着声明 ID 打开本页（/evidence?statements=…）。

### 报告证据引用表

穿透/系族报告导出时自动汇总结论涉及的声明证据：每条结论行内标注证据编号上标，
报告尾部附"证据引用表"（编号 → 声明 ID、来源文档、字段路径、内容哈希前 12 位、链接）。

## 9. v0.6 新功能：覆盖率趋势与证据时效（只提示，不认定）

### 覆盖率趋势区（/evidence 页）

覆盖率卡片下方新增趋势区：按声明生效年度分组的逐年覆盖率柱线图 + 表格
（年度/声明数/缺失/覆盖率/较上年），回答"覆盖情况在变好还是变坏"。
注意口径：逐年差值只是数据现状的对比，不构成数据质量"改进/恶化"的认定
（声明集合本身可能随时点变化）。

### 时效风险区（/evidence 页）

- **阈值选择**（1–30 年，默认 5）：列出"证据快照最近取证时间早于今天 − 阈值年"的声明，
  含声明链接、谓词、最近取证日期与证据年龄；恰好等于阈值不算陈旧；
- **无证据的声明不进本规则**：这类声明由上方覆盖率缺失口径呈现，避免同一缺陷重复报；
- **只提示、不认定**：时效候选仅说明"取证时间早于窗口"，是否影响结论权重由研究者
  自行判断；快照缺省取证时间按入库时间兜底；
- **扫描入库**（需 analyst 角色）：把当前候选幂等登记进复核通道（同声明已有未关闭的
  同名问题则跳过），viewer 登录时按钮隐藏并提示角色要求；
- **反查**：候选行的"反查"按钮把声明 ID 填入上方反查框，直接查看证据链。

### 报告中的时效标注

三页研究报告的证据引用表新增"快照时间"列：取证时间早于数据时点 − 阈值年的证据
标注"陈旧"（阈值与证据工作台同参数）；报告封面信息区附证据覆盖率摘要行。
两项信息获取失败时自动省略，不影响报告导出。

### E2E 后端限流提示

E2E 用例增至 19 项后，后端默认限流（每 IP 120 次/分）可能在高并发测试下触发 429。
本地跑全量 E2E 时建议提高限额启动后端：
`CG_RATE_LIMIT_PER_MINUTE=1200 uv run uvicorn cg_api.main:app --port 8301`。

> 部署在反向代理（nginx/Caddy）之后时，设 `CG_TRUST_PROXY=true` 限流才按
> X-Forwarded-For 区分真实客户端；默认不信任该头（可被伪造绕过限流）。

## 10. v0.7 新功能：质量总览（五维度）

证据工作台新增"质量总览"区，把数据质量聚成五个各自独立的计数：
覆盖率缺失（有没有证据）、时效（证据新不新鲜）、有效性（uscc 标识符校验位）、
唯一性（同键并行声明，疑似重复录入）、跨源一致性（多连接器比例冲突）。

- 前三条规则的口径：有效性只核查 uscc 命名空间（GB 32100-2015 校验位），
  lei 等其他命名空间未纳入；唯一性按时点有效声明分组，正常的历史更替不算；
  一致性只比较双方比例都给出的情形，任一侧缺失即不可比；
- 五维度全部"只提示、不认定"：计数和候选说明数据现状，不构成数据错误的认定；
- 候选行的"反查"按钮把声明 ID 填入上方反查框，直接看证据链；
- analyst 可点"登记复核"把三类候选幂等登记进复核通道（同候选不重复登记，
  已关闭的会再次登记）；时效维度的登记入口在下方"时效风险"区；
- 时效维度与"时效风险"区共用阈值参数（1–30 年）。
