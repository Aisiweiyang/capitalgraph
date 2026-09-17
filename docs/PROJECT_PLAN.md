# CapitalGraph CN 项目计划

状态：**阶段 0–7 全部完成（v0.1–v0.3.1 交付）；v0.4 资本系谱与风险传导完成（2026-09-13）；v0.5 资本异动与证据工作台完成（2026-09-14）** ｜ 最近更新：2026-09-14 ｜ 证据见 TEST_REPORT.md / DELIVERY.md

## 目标

面向中国企业研究的资本关系、股权穿透、实际控制候选识别、历史变更追踪与证据可视化平台。
所有结论均以"声明 + 证据"表达，最终受益所有人（UBO）仅输出候选，不替代法律认定。

## 环境基线与本次实测

| 项 | 要求 | 本机实测（2026-09-07） | 处理 |
| --- | --- | --- | --- |
| OS | Windows 11 + Docker Desktop | Windows 11，Docker 未安装 | ADR-002：本地默认 SQLite，提供 Compose 供有 Docker 环境使用 |
| Python | 3.12 | 3.12.13（uv 管理） | uv venv |
| Node | LTS | v24.19.0 / npm 11.17.0 | 前端工具链 |
| Git | 有 | 2.55.0 | 已初始化仓库（main 分支） |
| PostgreSQL | 主库 | 本机未装 | ADR-002：SQLAlchemy 双方言，PG 经 Compose 启用 |

工作目录初始盘点为空，但开发开始后（2026-09-07 23:08 起）检测到**另一并行会话在同一父目录**
搭建 AshareSignal Lab（A 股情绪量化研究项目，`asg-*` 包，见父级 `pyproject.toml` 与 `uv.lock`）。
为遵守"保留用户已有成果、不擅自覆盖"规则并避免两个 uv workspace 互相破坏，
CapitalGraph CN 改在独立子目录 `资本图谱/` 内实施（见 ADR-010），父目录其余文件一律未改动。

## 阶段计划与状态

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 0 | 盘点、需求矩阵、开源比较、许可证与风险 | 完成（OSS_EVALUATION 2026-09-07 核实） |
| 1 | ADR、领域模型、API contract、数据治理、威胁模型 | 完成（ADR-001~010，DATA_MODEL/THREAT_MODEL/DATA_GOVERNANCE） |
| 2 | 工程骨架、CI、Compose、迁移、观测 | 完成（uv workspace + CI + 迁移回环验证） |
| 3 | 证据核心、connector SDK、实体解析、时态存储 | 完成（62→64 项测试覆盖） |
| 4 | 图算法、资本关系 API、可视化 | 完成（穿透/环路/交叉持股/聚合/UBO + React/Cytoscape） |
| 5 | 人工复核、数据质量、RBAC、审计、导出 | 完成 |
| 6 | 全量测试、安全扫描、性能测试、恢复演练 | 完成（64 pytest + 3 vitest + 8 E2E 全绿；覆盖率 89.3%；恢复演练 ✓） |
| 7 | 清洁环境复现、修复、文档、演示 | 完成（DELIVERY.md 最短步骤实测） |

## 验收门槛（完成定义）

1. 软件真实启动（uvicorn + vite dev / 静态构建），健康检查通过。
2. 数据库迁移可执行（SQLite 实测 + PostgreSQL 迁移脚本就绪）。
3. 合成演示数据可导入（合成 connector，非真实商业数据）。
4. 核心流程可演示：检索 → 详情 → 穿透展开 → 证据 → 时间点 → 导出。
5. 测试实际通过并留有命令、退出码、数量、覆盖率证据。
6. 安全检查实际执行（授权/注入/XSS/SSRF/路径穿越/日志脱敏/依赖扫描）。

## 范围边界

首版不做：舆情预测、量化回测、真实交易。仅预留事件与证券标识的数据交换接口
（`packages/domain` 中 `Security`、事件类型占位与导入导出 schema）。

## v0.4 计划与验收清单（资本系谱与风险传导研究层）

目标：在单点穿透与区域流动之上补齐第三层研究能力——谁在控制一片企业（系族）、
风险如何沿担保/质押链传导、格局随时间演化，并能把研究结论一键导出为可分享报告。

| 切片 | 内容 | 状态 |
| --- | --- | --- |
| A 系族识别 | families 纯函数（union-find 并族）+ /families API + 资本系谱页 | 完成 |
| B 担保/质押风险传导 | synthetic 担保场景 + risk_chains 纯函数 + /risk API + 实体页风险区 + 复核页风险标记 | 完成 |
| C 时间演化回放 | 流动页按年回放（帧索引/串行预取/节流/取消） | 完成 |
| D 研究报告导出 | 三页一键导出自包含 HTML（纯前端） | 完成 |

验收清单（全部有实测证据，见 TEST_REPORT.md §v0.4）：

- [x] families/risk_chains 纯函数单测：聚类正确性、环连接并族、阈值边界、缺失比例/金额显式、确定性
- [x] /families 与 /risk API 集成测试：RBAC 401/403、参数校验、合成数据已知系族/担保圈断言、compute 幂等
- [x] 前端 vitest：系谱页逻辑、回放控件与纯逻辑、报告导出内容组装、风险展示格式化
- [x] 既有测试不回归：后端 83→129 项全绿；前端 8→24 项全绿；E2E 8 项全绿
- [x] 模块边界检查通过；合成场景确定性（固定 seed）；风险结果全部标注"算法候选"
- [x] 文档同步：ADR-015/016、ARCHITECTURE、DATA_MODEL、OSS_EVALUATION、USER_GUIDE、TEST_REPORT、DELIVERY、README

## v0.5 计划与验收清单（资本异动与证据工作台）

目标：把"已经算出来的结论"与"支撑它的证据、它的历史变化"连起来——什么时候变的（变更事件流）、
两个时点之间格局怎么变的（对比）、每条结论背后是哪份证据（证据工作台与 deep-link），
并补齐 v0.4 新页面的端到端质量。

| 切片 | 内容 | 状态 |
| --- | --- | --- |
| A 变更事件流 | events 纯函数（时态 diff 派生）+ /events 与 /entities/{id}/events + 全局异动页 + 实体页变更轨迹 | 完成 |
| B 格局对比 | families/flows diff 纯函数 + compare API + 系谱/流动页对比模式 + 对比报告 | 完成 |
| C 证据工作台 | 覆盖率统计 + /evidence/* API + 证据工作台页 + 全站 deep-link + 报告证据引用表 | 完成 |
| D 端到端质量收尾 | Playwright 补 v0.4/v0.5 页面 + 既有 8 项不回归 + 性能基线 | 完成 |

验收清单（全部有实测证据，见 TEST_REPORT.md §v0.5）：

- [x] events/diff 纯函数单测：事件类型正确性、比例增减前后值、缺失比例显式、两时点相同输入零事件、确定性
- [x] /events、/families/compare、/evidence/* API 集成测试：RBAC 401、参数校验 from<=to（422）、合成数据已知变更断言（2022-06-01 持股转移必产生持股失效+新增事件）
- [x] 前端 vitest：异动页筛选逻辑、对比视图差异计算、证据覆盖率统计、报告证据表组装
- [x] 既有测试不回归：后端 129→179 项全绿；前端 24→42 项全绿；E2E 8→16 项全绿
- [x] 模块边界检查通过；开源调研记录（deepdiff/时间线/事件溯源，OSS_EVALUATION v0.5 增量）；
      事件/对比/覆盖率结果全部标注"算法候选/研究用途"
- [x] 文档同步：ADR-017/018、ARCHITECTURE、DATA_MODEL、OSS_EVALUATION、USER_GUIDE、
      TEST_REPORT（实测命令与结果 + 2008 声明性能基线）、DELIVERY、README
- [x] 顺带修复 synthetic 分批缺陷（大规格跨批键解析/证据静默丢失），seed=42 断言零回归（ADR-018）

## v0.6 计划与验收清单（证据质量治理层：覆盖率趋势与时效提示）

目标：在证据工作台（覆盖率横切面 + 证据链反查）之上回答两个新问题：覆盖情况随时间
怎么变（趋势），证据"存在"是否还"新鲜"（时效）。两者都以"只提示、不认定"为纪律，
贯穿 API、工作台与研究报告（ADR-019/020）。

| 切片 | 内容 | 状态 |
| --- | --- | --- |
| A 覆盖率趋势 | coverage_timeline 纯函数 + /evidence/coverage/timeline + 工作台趋势区 | 完成 |
| B 证据时效 | captured_at 数据链路 + stale_evidence 纯函数 + /staleness 与 /staleness/scan + 工作台时效区 | 完成 |
| C 报告时效标注 | 报告证据表快照时间列/陈旧标注 + 覆盖率摘要行（失败降级） | 完成 |
| D 端到端 | E2E 3 新用例 + 种子库重建（captured_at 回填）+ 性能基线 | 完成 |

验收清单（全部有实测证据，见 TEST_REPORT.md §v0.6）：

- [x] coverage_timeline/stale_evidence 纯函数单测：逐年分组与合并、delta 首年/空年度显式 None、
      确定性；阈值边界（恰好等于不算陈旧、越界报错）、2 月 29 日平年平移、多快照取 max、
      无证据声明不进规则
- [x] /coverage/timeline、/staleness、/staleness/scan API 集成测试：RBAC（只读 viewer 可读、
      写通道 analyst+，viewer 401/403）、参数校验（years 1..30 之外 422）、scan 幂等
      （重复执行 created=0/skipped=N）、synthetic 质押证据 2019-01-01 已知候选断言
- [x] repo 层 max(fetched_at) 聚合测试；synthetic 质押证据回填 2019-01-01 且 seed=42 载荷零影响
- [x] 前端 vitest：趋势/时效展示格式化 6 项、报告快照列/陈旧标注/覆盖率摘要/降级 4 项；
      tsc -b 通过
- [x] 既有测试不回归：后端 179→203 项全绿（92.7%）；前端 50→60 项全绿；E2E 16→19 项全绿
- [x] 模块边界检查通过；性能基线（2008 声明：timeline p50 15.9ms / staleness p50 20.7ms，
      护栏 10s）；开源调研（GX/Soda Core/Deequ freshness 同族规则，均不引入，
      OSS_EVALUATION v0.6 增量）；趋势/时效结果全部标注"算法候选/只提示不认定"
- [x] 文档同步：ADR-019/020、ARCHITECTURE、DATA_MODEL、OSS_EVALUATION、USER_GUIDE、
      TEST_REPORT（实测命令与结果 + 性能基线）、DELIVERY、README、PROJECT_PLAN v0.6 验收清单

## v0.7 计划与验收清单（数据质量规则族）

目标：在覆盖率与时效之外补齐有效性 / 唯一性 / 跨源一致性三条质量规则，
五维度一处呈现，沿用"只提示、不认定"纪律（ADR-021）。

| 切片 | 内容 | 状态 |
| --- | --- | --- |
| A 有效性 | identifier_validity 纯函数（uscc 校验位，复用 is_valid_uscc） | 完成 |
| B 唯一性 | duplicate_statements 纯函数（同键并行 active 声明分组） | 完成 |
| C 跨源一致性 | cross_source_conflicts 纯函数（多连接器比例冲突） | 完成 |
| D 总览与看板 | GET /evidence/quality 五维度总览 + 工作台质量总览区 + E2E + 性能基线 | 完成 |

验收清单（全部有实测证据，见 TEST_REPORT.md §v0.7）：

- [x] 纯函数单测 7 项：仅核查 uscc 命名空间、排序确定性、同键并行分组、多源印证与
      缺失不可比不进一致性规则、同连接器差异不进规则、输入序鲁棒
- [x] API 集成测试 4 项：RBAC 401、五维度计数与既有单规则端点同源同值、
      注入非法 uscc 被有效性捕获、注入同键异连接器声明被唯一性+一致性同时捕获
- [x] repo 层 quality_statement_rows / identifier_rows（依赖方向：domain 不反向依赖
      capital_graph，行类型定义在 domain，router 适配）
- [x] 前端质量总览区（五计数卡 + 候选表/空态 + 一键反查 + 口径说明）；tsc/eslint 通过
- [x] 既有测试不回归：E2E 19→20 项全绿；vitest 60 项全绿
- [x] 性能基线（2008 声明：/evidence/quality p50 53.4ms / max 55.8ms，护栏 20s）
- [x] 文档同步：ADR-021、ARCHITECTURE、DATA_MODEL、USER_GUIDE、TEST_REPORT、
      DELIVERY、README、PROJECT_PLAN v0.7 验收清单

## v0.8 计划与验收清单（质量登记闭环）

目标：把 v0.7 三条质量规则从"只呈现"升级到"可处置"——统一登记复核通道
（ADR-021 修订），完成"提示 → 登记 → 人工复核"闭环。

- [x] POST /evidence/quality/scan（analyst+）：三类候选幂等登记 QualityIssue，
      rule_name 按维度取值；实体级/组代表两级幂等键；写审计
- [x] API 测试 3 项：RBAC 401/403、注入新实体非法 uscc 增量登记 + 二扫幂等、审计落库
- [x] 前端质量总览区"登记复核"按钮（analyst）/角色提示（viewer）+ 结果文案 helper 单测
- [x] E2E 21→22 项：analyst 登记按钮端到端（created→skipped，与库状态无关可重复）
- [x] 既有测试不回归：后端 239→242 项全绿（94.8%）；前端 60→61；E2E 22 项全绿

## v0.9 计划与验收清单（真实数据接入——阶段一原型）

目标：验证真实公开公告沿现有 CSV 连接器全链路承载（ADR-022），为规模化接入铺路。

| 切片 | 内容 | 状态 |
| --- | --- | --- |
| A 公告摘要形态 | CSV 连接器增 evidence_title/evidence_date 可选列 + ingest 来源文档归档 | 完成 |
| B 样例与联动 | 巨潮风格样例（含故意脏数据）+ 质量/时效规则在真实形态上的联动验证 | 完成 |

验收清单（全部有实测证据，见 TEST_REPORT.md §v0.9）：

- [x] 连接器：公告标题接 document_title、公告日期接 captured_at（ISO 解析，坏值拒绝留痕）；
      两列缺省行为与旧版完全一致（13 项既有 CSV 测试零改动通过）
- [x] ingest 来源文档归档：标题非空按（标题, URL) 建档，合成连接器行为零变化
- [x] 端到端：样例导入 4 实体/4 声明，证据链"来源文档"显示公告标题并可跳转真实 URL；
      公告日期驱动时效规则（1 年阈值出现候选）；编造 uscc 进有效性候选
- [x] 既有测试不回归：后端 245→249 项全绿；前端 74、E2E 22 项全绿

## v0.10 计划与验收清单（交叉验证规则族）

目标：在五维质量之上补两条交叉验证规则——股东比例合计（数学矛盾）与导入身份
一致性（同 ID 不同 uscc），扩展总览至六维度（ADR-023）。

- [x] ratio_sum_conflicts 纯函数：holds_shares 按公司聚合、缺失不猜值、
      合计偏低不报、超额降序确定性
- [x] csv_source 身份交叉校验：同 ext_id 不同非空 uscc → identity_conflict
      警告不拒行（先到者入主档）
- [x] /evidence/quality 六维度 + scan 登记比例合计冲突（组代表幂等）
- [x] 前端第六计数卡 + 比例超百表格（一键反查）
- [x] 端到端：真实形态样例注入 51%+60% 超百组合被精确标记（111%，2 成员）
- [x] 既有测试不回归：后端 245→**253 项**全绿；前端 74、E2E 22 项全绿

## v0.11 计划与验收清单（中文相关度检索，ADR-003 补记）

- [x] score_name_match 纯函数：规范化完全相等 1.0 / 前缀 0.9 / 包含 0.85 /
      2-gram Dice×0.8 分层，零依赖、确定性
- [x] /entities/search：score 字段 + 相关度降序（同分主档名序）+ 内存分页（候选上限 1000）；
      标识符回退命中 score=1.0
- [x] 前端 EntityHit 类型同步
- [x] 测试：评分分层边界 5 项、API 相关度排序与前缀居前 1 项
- [x] 既有测试不回归：后端 245→**254 项**全绿；前端 74、E2E 22 项全绿
