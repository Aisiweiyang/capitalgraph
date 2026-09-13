# ZCode 提示词五 CapitalGraph CN 资本异动与证据工作台（v0.5）

```text
你是 CapitalGraph CN 项目的全权技术负责人。项目现为 v0.4 基线（GitHub 私有仓库
Aisiweiyang/capitalgraph-cn，推送即 CI，当前保持绿色，最新交付提交 b1dfa72），已有能力：

- 时态声明模型 + 证据链（document→snapshot(sha256)→fragment），原始层只追加，修正走 supersede；
- 穿透引擎（纯函数）：向上/向下穿透、环路检测、交叉持股、聚合有效权益、UBO 候选（R1/R2）；
- 区域资本流动层 v0.3：省际流向/HHI/环路资金/年度趋势/省→行业，ECharts 地图 + 流向线；
- 系族识别层 v0.4：families.py 纯函数（union-find 并族、共同实控人、交叉持股环并族、
  阈值可配、无控制人分量显式计数）、/api/v1/families/*、资本系谱页（Cytoscape 子图 +
  被控路径 + 族间流向表）；
- 担保风险传导层 v0.4：risk_chains.py 纯函数（义务方向链条/互保圈/逐层传导，缺失金额
  显式不补值）、/api/v1/risk/*（chains/flags/compute 幂等写 RiskFlag，payload 带
  input_digest/算法版本/配置哈希）、synthetic 链式+环式担保圈与质押场景、CSV
  record_type 扩展 guarantee/pledge、实体页「风险传导」区、复核页「算法风险标记」；
- 时间回放：流动页按年回放（年末帧索引、串行预取 + 节流渲染 + AbortController）；
- 研究报告导出：穿透图/资本流动/资本系谱三页一键导出自包含 HTML（纯前端、dataURL
  图表、口径与免责声明、富文本转义）；
- RBAC（admin/analyst/viewer，JWT + argon2id）、审计、限流、复核队列、RiskFlag/QualityIssue；
- 后端 129 项测试 / 覆盖率 91.3%；前端 24 项 vitest；E2E 8 项；模块边界 CI 强制；
  文档齐全（ADR-001~016、PROJECT_PLAN v0.4 验收清单、TEST_REPORT/DELIVERY v0.4 实测）。

运行环境 Windows 11，CI 为 ubuntu-latest；界面中文，代码标识符英文；演示数据全部为
确定性合成。文档记录的已知限制（本轮输入）：报告不含证据原文；E2E 未覆盖 v0.4 新页面；
时态变更只可查单实体历史，无全局"异动"视角；系族/区域格局无跨时点对比。

## 1 本轮目标（v0.5：资本异动与证据工作台）

把"已经算出来的结论"与"支撑它的证据、它的历史变化"连起来：**什么时候变的（变更事件流）**、
**两个时点之间格局怎么变的（对比）**、**每条结论背后是哪份证据（证据工作台与 deep-link）**，
并把 v0.4 新页面的端到端质量补齐。

## 2 功能范围（四个纵向切片，每个切片独立可验收）

### 切片 A：变更事件流（时态 diff 派生）

1. 算法（packages/capital_graph 新增 events.py，纯函数、确定性、可单测）：
   - 输入为 from/to 两个时点的有效声明快照（仓储按 at 过滤，算法只做集合对比）；
   - 事件类型：声明新增（含新股东进入）、声明失效（superseded/到期/退出）、持股比例
     增减（带前后值与差值）、控制权获得/丧失（controls 边出现/消失）、担保新增/解除、
     质押新增/解除；
   - 事件只陈述"声明层面的变化"，不做动机推断；每条事件附 statement_ids 与证据引用键；
   - 同输入同输出（事件按类型/主体/时间排序），缺口（比例缺失）显式标注不比较数值。
2. API：/api/v1/events?from=&to=（全局流，分页）、/api/v1/entities/{id}/events
   （单实体，viewer 可读）；返回附口径说明与输入时点。
3. 前端：全局「异动」页（时间线列表 + 类型筛选 + 点击跳转相关实体）；实体详情页
   新增"变更轨迹"区（该实体的前后对比摘要）。

### 切片 B：格局对比（系族与区域 at1 vs at2）

1. 算法（families.py/flows.py 增量纯函数，不改变既有函数签名与行为）：
   - families diff：族出现/消失、控制人变更、成员增减清单、规模/省份覆盖/环路数变化；
   - 区域对比：跨省金额、HHI、流向条数的两时点差值与新增/消失流向对；
   - 复用切片 A 的事件口径解释"为什么变"（可选关联，不强求）。
2. API：/api/v1/families/compare?from=&to=、/api/v1/flows/compare?from=&to=（viewer 可读）。
3. 前端：资本系谱页与资本流动页新增"对比"模式（选两个时点 → 双列/差异高亮视图）；
   报告导出支持对比上下文（kind 增加 compare 或参数化）。

### 切片 C：证据工作台

1. 统计（纯函数 + /api/v1/evidence/coverage）：声明证据覆盖率 = 有证据片段的 active
   声明占比，按谓词/连接器/年度分组；缺失证据的声明数显式列出（不修复、只呈现）。
2. 浏览：/api/v1/evidence/documents（文档→快照→片段导航）+ 前端「证据工作台」页
   （按来源文档浏览片段、按声明反查证据、覆盖率卡片）；全站 deep-link：穿透路径边、
   系族成员路径、风险标记 payload 中的 statement_ids 一键打开对应证据（复用现有
   实体页证据弹层逻辑）。
3. 报告增强：导出 HTML 附"证据引用表"（statement_id → 文档标题/字段路径/内容哈希
   前 12 位/链接），并在每条结论行内标注证据编号上标。

### 切片 D：端到端质量收尾

1. Playwright 新增用例：系谱页列表→详情、实体页风险传导区、流动页回放（拖动滑块断言
   帧年份变化）、任一页报告下载（断言 .html 文件与文件名）、异动页与证据工作台；
2. 既有 8 项 E2E 不得回归；性能基线补测：2000 声明规模下 /events 与 /families/compare
   的响应时间（记录到 TEST_REPORT，超阈值只记录并在已知限制说明，不阻塞交付）。

## 3 开源调研约束（编码前核实并记录 docs/OSS_EVALUATION.md 增量）

- deepdiff 等通用 diff 库（MIT）：**大概率自研**——声明快照 diff 是有序集合对比，
  自研约百行且可控；仅当边界情况（多重集/比例容差）自研复杂度超阈值时按 ADR 引入；
- 时间线可视化：优先自研（HTML/CSS 列表）或 ECharts 既有图型，不引入新前端依赖；
  若引入组件库需 ADR-017 记录取舍；
- 事件溯源/CQRS 框架：**不引入**（声明层已是 append-only + supersede，事件是派生只读
  视图，无写入路径需求）；记录调研结论即可；
- 任何采用记录仓库/版本/许可证/用途；不新增后端 Python 运行时依赖（保持 ADR-002/014/015
  纯函数路线）。

## 4 硬约束

1. 每个切片先写测试再实现：events/diff 纯函数单测（事件类型正确性、比例增减前后值、
   缺失比例显式、两时点相同输入零事件、确定性）；/events、/families/compare、
   /evidence/* API 集成测试（RBAC 401/403、参数校验 from<=to、合成数据已知变更断言
   ——如历史变更场景 persons[0]→persons[1] 的 2022-06-01 持股转移必产生"控制/持股
   变更"事件）；前端 vitest（异动页筛选逻辑、对比视图差异计算、证据覆盖率统计、报告
   证据表组装）；既有 129 项后端 + 24 项前端 + 8 项 E2E 不得回归。
2. 模块边界检查（scripts/module_graph.py）必须保持通过；CI 推送后必须绿。
3. 合成数据新增场景必须确定性（固定 seed 可复现）且不得破坏既有 seed=42 断言
   （新增场景用独立 rng 或新谓词，文档写明）；保持演示口径标注。
4. 风险/对比/覆盖率类结果一律标注"算法候选/研究用途"，不构成信用、法律或投资结论。
5. 文档同步：docs/PROJECT_PLAN.md（v0.5 计划与验收清单）、docs/DECISIONS.md
   （ADR-017 事件派生口径、ADR-018 证据覆盖率与 deep-link 口径）、ARCHITECTURE.md、
   DATA_MODEL.md、OSS_EVALUATION.md、USER_GUIDE.md、TEST_REPORT.md（实际命令与结果）、
   DELIVERY.md（v0.5 交付）、README（功能亮点）。未运行的事项不得标为完成。
6. 交付后推送 GitHub 并确认 CI 绿；最终回复按惯例列出：架构取舍 / 功能与文件位置 /
   实际测试证据 / 开源借鉴 / 已知限制与下一步建议。

## 5 实施顺序

阶段 A：提示词自审（可测性/口径清晰度）→ 读 docs/PROJECT_PLAN.md、docs/DECISIONS.md、
docs/TEST_REPORT.md 与 git log，运行 uv run pytest tests -q 与
uv run python scripts/module_graph.py 做最小状态检查 → 切片 A（事件）后端 → API → 前端页。
阶段 B：切片 B（对比）。阶段 C：切片 C（证据工作台）。阶段 D：切片 D（E2E 收尾）。
每切片结束跑对应测试；全部完成后跑全量验证（pytest --cov / vitest / build / playwright /
module_graph / bandit / secret_scan）→ 文档 → 小步提交 → 推送 → 确认 CI 绿。
除真正阻塞外不停下来等待批准；中断续跑提示词见文末。
```

中断续跑提示词：

```text
继续执行 CapitalGraph CN v0.5 资本异动与证据工作台任务。先读 docs/PROJECT_PLAN.md、
docs/DECISIONS.md、docs/TEST_REPORT.md 与 git log，运行 uv run pytest tests -q 与
uv run python scripts/module_graph.py 做最小状态检查，从第一个未完成的切片/验收项继续。
不要重新初始化、不要重复已通过工作、不要只汇报计划。本轮结束前更新文档并实际运行相关测试。
```
