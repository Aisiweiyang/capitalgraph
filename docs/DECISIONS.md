# 架构决策记录（ADR）

每条决策含：背景、决策、代价、状态。状态变更需追加新 ADR 而非改写旧结论。

## ADR-001 Monorepo + uv workspace（2026-09-07，已采纳）

- 背景：提示词推荐 `apps/api`、`apps/web`、`workers`、`packages/*` 目录；团队单人，需避免多仓同步成本。
- 决策：单 Git 仓库；Python 侧用 uv workspace（`packages/*`、`apps/api`、`workers` 为成员），
  前端 `apps/web` 独立 npm 工程。
- 代价：根配置略复杂；收益：原子提交、版本一致、CI 简单。

## ADR-002 单一事实源 = 关系库；图遍历在 Python 层（2026-09-07，已采纳）

- 背景：本机无 Docker/PostgreSQL/Neo4j；提示词要求"只能有一个事实真相源"，且需本地可运行可测。
- 决策： SQLAlchemy 2.0 双方言支持（SQLite 本地开发/测试，PostgreSQL 生产，经 `infra/docker-compose.yml` 提供）；
  股权穿透、环路检测、聚合等图计算实现于 `packages/capital_graph`（纯函数、确定性、可单测），
  输入为从声明表加载的边集合，不依赖数据库递归方言。
- 代价：超大规模需内存约束（已设节点/路径上限与超时）；收益：算法与存储解耦、可确定性复现、双库行为一致。
- 撤销条件：单机内存无法容纳活动边集或延迟不达标时，重评 Neo4j Community（Apache-2.0）做投影缓存，事实源不变。

## ADR-003 搜索先用数据库原生能力（2026-09-07，已采纳）

- 背景：首版数据为合成与样例规模；专用搜索服务增加运维面。
- 决策：检索走规范化字段精确匹配 + 前后缀/包含查询；SQLite 用 FTS5/LIKE，PostgreSQL 用 pg_trgm + 全文
  （迁移中含 PG 侧索引，SQLite 侧降级为 LIKE）。接口抽象在 `cg-domain.search`。
- 代价：中文分词弱；收益：零额外服务。数据量证明需要时再引入 Meilisearch/ES（另行 ADR）。

## ADR-004 对象存储本地适配器（2026-09-07，已采纳）

- 决策：`cg-connectors.storage` 定义 `ObjectStore` 协议；默认 `LocalObjectStore`（内容寻址目录），
  接口对齐 S3 语义（put/get/exists/delete + sha256 键），后续可加 MinIO 实现而不改调用方。
- 代价：无；收益：本地零依赖，原文持久化可通过 `CG_STORE_RAW_DOCUMENTS=false` 关闭（合规）。

## ADR-005 Worker 采用简单幂等循环，不引入 Dagster（2026-09-07，已采纳）

- 决策：`workers/` 提供 CLI：单任务执行与常驻轮询两种模式；任务表记录状态、幂等键、重试次数、
  指数退避；失败隔离在任务级。Dagster 触发条件：任务种类 > 5 且需资产级血缘（记录于 OSS_EVALUATION）。
- 代价：无编排 UI；收益：可测试、依赖少。

## ADR-006 认证鉴权：JWT + 后端强制 RBAC（2026-09-07，已采纳）

- 决策：HS256 JWT（`CG_SECRET_KEY` 环境变量），角色 admin/analyst/viewer；
  依赖注入层按路由声明要求角色，默认拒绝；前端隐藏只是体验优化不作为安全边界。
  审计中间件记录 actor/action/target/request_id/result，追加写。
- 代价：无 SSO；收益：最小可依赖集、可测。

## ADR-007 前端用 Vite + React SPA 而非 Next.js（2026-09-07，已采纳）

- 背景：提示词写 "React/Next.js"。
- 决策：采用 Vite + React + TypeScript strict。理由：纯内网工具型应用，无 SSR/SEO 需求；
  构建产物可由 FastAPI 直接静态托管，本地演示只需一个服务进程；Playwright E2E 更简单。
- 代价：放弃 Next.js 生态；React 要求满足。若未来需要服务端渲染再评估。

## ADR-008 模型协作规范（2026-09-07，已采纳为流程）

- 本会话未接入 DeepSeek 工具，由 ZCode 直接实现。若后续接入：每次委派必须提供
  接口签名、输入输出示例、失败语义、测试清单、完成定义；回收代码必须通过
  领域模型一致性、安全（§7）与许可证三道复核，并由 ZCode 亲自运行测试。

## ADR-009 中文本地化与规范化（2026-09-07，已采纳）

- 决策：实体名称规范化：全半角、大小写、括号格式、常见公司后缀剥离（“有限公司”等）生成 `norm_name`；
  统一社会信用代码按 GB 32100-2015 校验位验证；匹配不得仅凭名称（提示词 §5 硬约束），
  名称相似度只产生候选，需标识符或人工复核确认。

## ADR-010 独立子目录隔离并行项目（2026-09-07，已采纳）

- 背景：开发启动后发现另一并行会话在同一父目录搭建 AshareSignal Lab（asg-* uv workspace，
  占用根级 pyproject.toml/uv.lock 与 packages/、apps/api 目录名）。
- 决策：CapitalGraph CN 全部成果收敛于 `资本图谱/` 子目录，内含独立 Git 仓库、独立 uv workspace、
  独立 npm 工程；绝不读写父目录中 asg-* 相关文件。
- 代价：父目录与本项目各有仓库，需分别操作；收益：零冲突，`资本图谱/` 整体可搬移到任意路径。
- 提示词中"当前目录"解释为本项目子目录；最终交付物均位于 `资本图谱/` 内。

## ADR-011 文档收敛 docs/ 与产物出库（2026-09-11，已采纳）

- 背景：v0.1.0 交付后进入 GitHub 发布阶段，根目录并存 README、LICENSE 与 8 份交付文档 + SBOM，
  且 `tsconfig.tsbuildinfo`、`e2e/.auth-state.json` 等本地产物被误跟踪。
- 决策：`ARCHITECTURE / DATA_MODEL / DATA_GOVERNANCE / THREAT_MODEL / OSS_EVALUATION /
  TEST_REPORT / DELIVERY / THIRD_PARTY_NOTICES / SBOM.cdx.json` 全部收敛到 `docs/`；
  根目录只保留 README.md、LICENSE 与工程配置。`scripts/sbom.py` 输出路径同步改为 `docs/`；
  构建产物与本地认证状态加入 `.gitignore` 并移出索引。跨文档链接已同步更新。
- 代价：外部旧链接（若有）需按新路径访问；收益：根目录即工程入口，文档单一存放点，
  符合 GitHub 仓库浏览习惯，整体可搬移性不受影响（仓库内自包含）。

## ADR-012 模块边界 CI 强制（2026-09-11，已采纳）

- 背景：模块化迁移承诺要求每个 workspace 成员可独立抽取；人工核对 import 与 pyproject 声明易失真
  （本次即发现 2 处漏声明、1 处冗余声明）。
- 决策：`scripts/module_graph.py` 用 AST 扫描全部成员的实际内部导入，与 pyproject 声明对照，
  不一致即退出非零；CI 后端任务在测试前运行。ARCHITECTURE/DATA_MODEL 增加 Mermaid 图（GitHub 原生渲染），
  新增 MIGRATION.md 记录整体迁移与单模块抽取路径。
- 代价：新增一道 CI 检查（秒级）；收益：依赖声明与代码事实持续一致，模块可迁移性可验证而非口头承诺。

## ADR-013 图表与中国地图：ECharts 5.6（Apache-2.0），GeoJSON 内置（2026-09-12，已采纳）

- 背景：v0.3 需要中国省级行政区划着色（choropleth）、省际流向线、桑基与常规统计图表。
- 决策：采用 Apache ECharts。按需引入 `echarts/core` + Map/Lines/Line/Bar/Sankey 图型 +
  Geo/VisualMap/Tooltip/Grid/Legend 组件 + CanvasRenderer，控制打包体积。地图 GeoJSON 取自
  DataV.GeoAtlas（areas_v3/100000_full.json，2026-09-12），一次性内置为
  `apps/web/src/assets/china.json`，运行时零外部地图服务依赖。
- 版本：实测 v6.1.0 中 `lines` 系列（geo 坐标系）与增量渲染层在离屏/后台标签场景不刷新，
  且 v6 默认主题与坐标系统架构变化大；钉在 v5.6.0（同一套按需引入 API）。升级 v6 的条件：
  上游确认修复 lines-on-geo + 增量层导出问题并通过本仓库可视化回归（含离屏导出）。
- 已知坑（记入代码注释）：lines 的颜色必须放在数据项级 lineStyle.color，series 级 color
  不传导；lines/sankey 需 `animation:false`/`progressive:0` 避免动画进度停 0% 不绘制。
- 代价：echarts 使前端产物增重约 330KB(gzip ~110KB)；收益：一个库覆盖全部图表需求且中文文档完善。
- 合规：地图数据仅研究演示用途；正式出版物须使用自然资源部标准地图服务（审图号）数据（MAP_DATA_SOURCE.md）。

## ADR-014 区域资本流动聚合口径（2026-09-12，已采纳）

- 范围：流动=资本放置类声明（holds_shares/invests_in）；controls 是治理关系，不计入流动。
- 时点：仅统计 status=active 且 `valid_from <= at < valid_to` 的声明（仓储 flow_rows 过滤）。
- 跨省判定：subject 与 object 均有 region_code 且不相等；任一方缺失 → 丢弃并以
  unknown_region_edges 显式计数；同省边计入 internal_edges，不进流向。
- 金额：只使用结构化 amount_scaled（万元×100 缩放整数，AMOUNT_SCALE）；缺失金额的边计入
  边数与 amount_missing_edges，不计入金额合计，绝不补值。字符串 amount 列仅为来源原始记录。
- 比例：total_share_percent 为直接持股比例求和（百分数），缺失边计入 ratio_missing_edges；
  聚合有效权益仍属穿透分析（capital_graph.analysis），流动层不做路径乘积。
- HHI：各省流出金额份额（百分点）平方和，0..10000；流出总额为 0 时输出 None。
- 环路资金：复用 capital_graph.detect_cycles，统计环路中跨省边数与其中有金额边数。
- 依赖：全部为 cg-capital-graph 纯函数（flows.py），零新增后端依赖；networkx 暂不引入。

## ADR-015 图谱库取舍：系族子图继续用 Cytoscape，G6 不引入（2026-09-13，已采纳）

- 背景：v0.4 资本系谱页需要"控制人居中、成员分群着色"的族内子图。提示词允许在 Cytoscape
  表达吃力（需要 combo/分群布局）时对 antvis/G6（MIT）做隔离评估。
- 实测结论：单族规模小（演示数据 ≤ 30 节点），Cytoscape breadthfirst 布局以控制人为根
  即可表达层级，节点按 region_code 稳定取色、控制边虚线、环路节点红框——不构成切换
  图谱库的理由。引入 G6 反而增加 ~200KB 级依赖与双图 API 心智成本。
- 决策：系族子图以独立组件 `FamilyGraph.tsx` 封装（复用穿透图的交互模式与样式语言），
  继续基于 Cytoscape；G6 不引入。未来若出现真实的 combo/分群布局需求（万级成员、
  动态聚缩），再按本 ADR 触发条件做隔离评估（独立组件、不影响穿透图）。
- networkx 同轮复核：并族用 union-find + BFS（共同可达成员）即可，复杂度 O(V+E)，
  无需 Louvain 社群发现；继续保持 cg-capital-graph 零第三方运行时依赖（ADR-002/014）。

## ADR-016 系族识别与担保风险传导口径（2026-09-13，已采纳）

**系族识别（cg-families/1.0.0，`families.py` 纯函数）**
- 控制类边 = controls 声明 + 比例 ≥ 阈值（默认 50%，可配置，`min_control_ratio_percent`）
  的 holds_shares 声明；controls 的控制语义不由比例推导（与穿透引擎一致）；
  缺比例的 holds_shares 不构成控制边，以 `missing_ratio_holding_edges` 显式计数。
- 控制人根仅限非企业实体（默认 person/government_body，可配置）；kind 缺失或企业实体
  保守地不作根（宁缺毋错，不编造控制人）。
- 聚类：从每个控制人沿控制方向 BFS 收集可达实体并记录被控路径；同一实体被多个控制人
  可达 → 并族（共同实控人）。交叉持股环上的实体被环内外控制人共同可达，因此随共同
  可达自然并族——无需单独的互可达检测（union-find 小根为父，与合并顺序无关）。
- 无控制人可达的连通分量不成族，实体计入 `unassigned_entity_count` 显式输出。
- 族 ID = 族内控制人集合排序最小者；族内密度 = 控制类内部边数 / (n·(n-1))，n<2 为 None；
  跨省分布含 `region_unknown` 计数；族内环路复用 detect_cycles（有界）。
- 护栏：单控制人遍历成员数/路径深度有界，命中打 `truncated`。同输入同输出（全排序）。
- 族间流向（`family_flows`）：流动边按（族，族）分组聚合金额；同族边与任一端无族边
  分别显式计数，不进族间聚合；缺失金额边显式计数，绝不补值（沿用 ADR-014 金额口径）。

**担保风险传导（cg-risk-chains/1.0.0，`risk_chains.py` 纯函数）**
- 担保边 = 时点有效 provides_guarantee 声明（subject=担保人，object=被担保人），
  金额用结构化 amount_scaled（万元×100）；缺失金额显式计数，绝不补值。
- 链条沿"义务方向"（被担保人 → 担保人）回溯：下游出险 → 上游担保人受累；
  环 = 声明方向（担保人→被担保人）上的环路即互保圈，输出规范化（最小节点起头、
  含闭合收尾、去重排序）。
- 传导：出险集合沿义务方向 BFS 逐层扩散（受累去重），每层名义金额 = 引发该层担保边
  金额合计；任一边缺金额 → 该层名义 None；总计仅当全部金额齐备时输出。
- "出险"定义 = 被标 open 状态 RiskFlag 的实体；API `POST /risk/compute` 支持显式
  distressed 参数做模拟。结果写 risk_flags 表（flag_type 枚举扩展 guarantee_cycle /
  guarantee_chain_exposure），payload 记录 input_digest（边集内容摘要，与顺序无关）/
  algorithm_version / config_hash；同 (类型, 主体, 输入摘要) 的 open 标记幂等去重。
- 质押 pledges_shares 不参与链式传导，在实体详情页作为风险敞口列表展示（比例与金额
  缺失均显式）。
- RBAC：chains/flags 查询 viewer 可读；compute 需 analyst，写审计日志。

**时间回放与报告导出（前端口径）**
- 回放：以 /flows/timeline 年份为帧索引，逐帧以"年末日期"（YYYY-12-31，左闭右开区间
  含全年声明）请求 /flows/summary 与 /flows/regions；请求预算 = 年数 × 2；串行预取 +
  节流渲染（800ms/帧）+ AbortController 取消（取消为正常路径，静默停止）。
- 报告：纯前端组装自包含 HTML（内联 CSS、图表 dataURL 内嵌、文本全转义、图表仅接受
  data:image 前缀），含生成时间/时点 at/阈值/算法版本/配置哈希/免责声明，零后端依赖。
