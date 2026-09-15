# 开源项目评估

核实日期：2026-09-07，来源：GitHub API（仓库元数据）与仓库 LICENSE 文件。结论约束：不按星数选型、不拼接多项目；只借鉴 schema/provider/provenance/插件/测试/文档模式。

| 仓库 | 许可证 | 最近推送 | 星数 | 活跃度 | 本项目采用结论 |
| --- | --- | --- | --- | --- | --- |
| alephdata/followthemoney | MIT | 2026-02-28 | 290 | 维护中 | **参考本体**：实体类型（LegalEntity/Person/Company/Ownership…）、规范化与验证思想。借鉴其"声明式 schema + 校验"模式；不引入运行时依赖（其模型面向调查文档，与本项目时态声明模型差异大） |
| openownership/data-standard | Apache-2.0（schema 内容，README/LICENSE 明示） | 2026-09-02 | 81 | 活跃 | **重要参考**：BODS 的 statement（ownership/control）、interestedParty、`statementDate`、证明文件与来源表达。本项目声明模型字段命名与语义对齐其概念 |
| opensanctions/opensanctions | 代码 MIT（数据集另有条款） | 2026-09-07 | 797 | 活跃 | **参考**：可追溯采集（crawl→store 原始→clean→export 管线）、数据质量报告模式。仅借鉴模式，不引入框架 |
| opensanctions/nomenklatura | MIT | 2026-09-06 | 265 | 活跃 | **参考实体解析**：candidate 生成、评分、人工决策（judgement: positive/negative/unsure）与版本记录。本项目 `resolution_candidates/decisions` 对齐其决策语义，实现自研（避免引入其服务栈） |
| opensanctions/yente | MIT | 2026-09-07 | 176 | 活跃 | 参考其 API 匹配接口形态；本项目不使用 Elasticsearch，不引入 |
| alephdata/aleph | MIT | 2026-02-20 | 2425 | 核心维护已收敛（与提示词判断一致） | **仅参考**文档与检索/调查工作流；不作为底座 |
| neo4j/neo4j | GPL-3.0（Community） | 2026-08-24 | 17202 | 活跃 | **暂不引入**：GPL 传染性要求服务隔离且通过 ADR 明确义务；当前无规模需求（ADR-002）。仅可作为独立服务部署选项，无代码链接 |
| cytoscape/cytoscape.js | MIT | 2026-09-06 | 11200 | 活跃 | **直接采用**：前端图可视化核心依赖（npm 包） |
| datahub-project/datahub | Apache-2.0 | 2026-09-07 | 12644 | 活跃 | 仅参考元数据血缘/治理**思想**；不引入平台 |
| dagster-io/dagster | Apache-2.0 | 2026-09-04 | 16122 | 活跃 | **暂不引入**（ADR-005）：任务种类少，简单幂等 worker 足够；触发条件见 ADR |

## 许可证风险分级

- **安全（MIT/Apache-2.0）**：followthemoney、opensanctions（代码）、nomenklatura、yente、aleph（参考不依赖）、cytoscape.js、datahub（参考不依赖）、dagster（暂不依赖）、BODS schema。
- **需谨慎（GPL/AGPL/SSPL）**：neo4j Community（GPL-3.0）。处理：不依赖、不链接、不集成其客户端驱动到本项目进程；若未来部署，作为独立进程 + ADR 记录义务。
- **注意**：opensanctions/nomenklatura/yente 的**数据**许可证与代码许可证不同；本项目不使用其数据，仅借鉴代码模式。

## 采用清单（运行时实际依赖的第三方）

见 `THIRD_PARTY_NOTICES.md`（随依赖锁定生成）。当前运行时采用：`cytoscape.js`（MIT）。
其余为模式借鉴，无代码复制；若后续出现代码级改编，按提示词 §3 记录仓库、commit、文件、许可证与修改。

## v0.3 增量调研（2026-09-12，资本流动与地图可视化）

核实方式：WebSearch（官方站/GitHub）、npm 安装实测。结论：

| 仓库/资源 | 许可证 | 版本/核实 | 采用结论 |
| --- | --- | --- | --- |
| apache/echarts | Apache-2.0 | v6.1.0（官方站/releases，2026-09-12 核实）；实际安装 5.6.0 | **采用（图表+中国地图）**。按需引入 echarts/core。v6 实测发现 lines-on-geo/增量层在离屏场景不刷新的兼容风险，故钉在久经考验的 v5.6.0（同一套按需引入 API，迁移成本零）；v6 触发回归后可升（ADR-013） |
| DataV.GeoAtlas（阿里云） | 公开地图数据（non-商业演示） | areas_v3 100000_full.json，2026-09-12 下载 | **采用（内置）**：`apps/web/src/assets/china.json`（35 要素含港澳台）。见 assets/MAP_DATA_SOURCE.md 来源与合规声明；正式出版须换用自然资源部标准地图（审图号） |
| antvis/G6 | MIT | v5（LICENSE 核实） | **借鉴不引入**：股权穿透场景的布局/组合/插件设计是 Cytoscape 图的演进参考；触发条件记于 ADR-013 |
| networkx/networkx | BSD-3-Clause | 3.6.1（2025-11 release） | **暂不引入**：度中心度/HHI 等在 cg-capital-graph 纯函数自研（符合 ADR-002 零依赖图计算）；需要中介中心性/最大流且规模超阈值时再评估（ADR-014） |
| OpenSPG（Ant Group × OpenKG） | Apache-2.0（工程庞大） | 2026-09-12 核实 | 仅参考其金融领域知识图谱建模思路；不引入 |
| jm199504/Financial-Knowledge-Graphs | 教学项目 | 2026-09-12 核实 | 参考其金融 KG 构建流程叙述；无代码采用 |

## v0.4 增量调研（2026-09-13，系族与风险传导）

核实方式：GitHub 仓库元数据与 LICENSE 复核（提示词 §3 指定对象）。结论：

| 仓库/资源 | 许可证 | 版本/核实 | 采用结论 |
| --- | --- | --- | --- |
| networkx/networkx | BSD-3-Clause | 3.6.1（2026-09-13 复核） | **本轮仍自研，不引入**：系族聚类 = union-find + BFS（O(V+E)），担保链/环 = 迭代 DFS 三色标记（复用环路检测思想），无最短路/流/社群发现需求；引入 networkx 反而破坏 cg-capital-graph 纯函数零依赖边界。触发条件不变：需要 Louvain/中介中心性且规模超阈值时按 ADR 评估 |
| antvis/G6 | MIT | v5（2026-09-13 复核） | **评估后不引入（ADR-015）**：系族子图规模小（≤30 节点），Cytoscape breadthfirst + 区域着色足够表达；G6 的 combo/分群布局为未来万级成员场景的触发条件，届时做独立组件隔离评估 |
| apache/echarts | Apache-2.0 | 5.6.0（沿用） | 继续沿用（ADR-013），回放复用既有 map/lines 系列，无新图型 |
| cytoscape/cytoscape.js | MIT | 3.30（沿用） | 继续沿用；新增 FamilyGraph 组件（独立封装，不影响穿透图） |

无新增后端 Python 运行时依赖（ADR-002/014 纯函数路线保持）；无代码级复制，均为模式借鉴或既有依赖的增量使用。

## v0.5 增量调研（2026-09-14，变更事件流与证据工作台）

核实方式：GitHub 仓库元数据与 LICENSE 复核（提示词 §3 指定对象）。结论：

| 仓库/资源 | 许可证 | 版本/核实 | 采用结论 |
| --- | --- | --- | --- |
| seperman/deepdiff | MIT | 8.x（2026-09-14 复核） | **大概率自研，不引入**：声明快照 diff 是按 (subject, predicate, object) 键的有序集合对比，自研约百行纯函数（events.py），且需要"比例缺失显式不比较"等业务口径，通用 diff 库反而要为其配置.ignore 不比较项与容差；仅当未来出现多重集/浮点容差等边界使自研复杂度超阈值时按 ADR 引入 |
| 时间线可视化（vis-timeline / react-chrono 等） | MIT | 2026-09-14 复核 | **自研（HTML/CSS 列表 + 类型筛选 chips），不引入**：异动页为线性事件列表，无拖拽缩放/群组泳道需求；引入组件库违背"不新增前端依赖"约束；时间线语义已在 eventsDisplay.ts 展示口径内表达 |
| 事件溯源 / CQRS 框架（EventStoreDB、Axon、kurrent 等） | 多为 OSS/商用混合 | 2026-09-14 复核 | **不引入**：声明层已是 append-only + supersede（原始层只追加），事件是由两时点有效快照派生的只读视图，无写入路径、无投影重放需求；记录调研结论即满足约束 |
| apache/echarts、cytoscape/cytoscape.js | Apache-2.0 / MIT | 5.6.0 / 3.30（沿用） | 继续沿用既有版本，零新增前端依赖 |

无新增后端 Python 运行时依赖（ADR-002/014/015 纯函数路线保持）；无代码级复制，均为模式借鉴。

## v0.6 增量调研（2026-09-15，证据质量治理：覆盖率趋势与时效规则）

核实方式：GitHub 仓库元数据与 LICENSE 复核（核实日期 2026-09-15）。数据质量规则引擎的
主流实现与本项目"覆盖率 + 时效"两条规则的对应关系：

| 仓库/资源 | 许可证 | 版本/核实 | 采用结论 |
| --- | --- | --- | --- |
| great-expectations/great_expectations | Apache-2.0 | 1.x（2026-09-10 发版，2026-09-15 复核） | **不引入，规则语义借鉴**：GX 的 `expect_column_values_to_be_between`/`expect_column_pair_values_a_to_be_greater_than_b` 等 Expectation 与本项目"阈值 + 窗口"规则同族；其数据资产级 Checkpoint 运行模型依赖 pandas/Spark 执行后端与 YAML 配置体系，对单服务 SQLAlchemy 架构过重；覆盖率/时效各约百行纯函数即可表达，且需要"缺失显式、恰好等于阈值不算陈旧"等业务口径 |
| sodadata/soda-core | Apache-2.0 | 4.18.0（2026-09-15 复核） | **不引入**：SodaCL 的 `freshness(column) < 1d` / `missing_count(x) = 0` 检查语法与本项目时效/缺失规则同族（ADR-020 口径说明已注明）；同样因执行引擎与配置体系依赖（需 data source 配置 + checks YAML）不匹配，纯函数路线（ADR-002）保持零新增运行时依赖 |
| awslabs/deequ | Apache-2.0 | 2.0.14-spark-4.0（2026-09-15 复核） | **不引入**：Completeness/Freshness analyzers 语义同族，但 Deequ 绑定 Spark 运行时（JVM/分布式计算），SQLite 单机服务场景完全不匹配；其"metrics repository + anomaly detection"思路留作大规模阶段的评估备选（按 ADR-002 触发条件再评估） |
| pydantic/pydantic、sqlalchemy 等 | MIT / MIT | 沿用 | 沿用既有版本，零新增后端 Python 运行时依赖 |

**同族规则的口径对齐**：三者的 freshness/时效检查均默认"阈值 + 窗口"语义；本项目在
ADR-020 中补充了三处显式业务口径——恰好等于阈值不算陈旧（严格小于）、无证据声明不进
时效规则（归覆盖率缺失通道）、时效只提示不认定（ISO/IEC 25012 Currentness：新度要求
取决于使用语境）。均为模式借鉴，无代码级复制。
