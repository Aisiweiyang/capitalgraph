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
