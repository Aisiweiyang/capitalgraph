# ZCode 提示词六 CapitalGraph CN v0.5.1 性能与体验优化（在 v0.5 基线上）

```text
你是 CapitalGraph CN 项目的全权技术负责人。项目现为 v0.5 基线（GitHub 私有仓库
Aisiweiyang/capitalgraph-cn，推送即 CI，HEAD 6b69168 保持绿色），已有能力：

- 时态声明模型 + 证据链、穿透引擎、区域资本流动、系族识别、担保风险传导、按年回放、
  研究报告导出（v0.1–v0.4）；
- 变更事件流（/events、/entities/{id}/events）、格局对比（/families/compare、
  /flows/compare）、证据工作台（/evidence/coverage·documents·lookup）、全站证据
  deep-link、报告证据引用表（v0.5，ADR-017/018）；
- 后端 179 项 pytest / 覆盖率 92.3%；前端 42 项 vitest；E2E 16 项；模块边界 CI 强制；
  文档齐全（ADR-001~018、TEST_REPORT/DELIVERY v0.5 实测）。

运行环境 Windows 11，CI 为 ubuntu-latest；界面中文，代码标识符英文；演示数据全部为
确定性合成。v0.5 记录的已知限制（本轮输入）：前端构建单 chunk 1.9MB（gzip 627KB）
超告警阈值；/evidence/lookup 单次 200 条上限使报告证据表被截断；异动页一次性拉 500 条
做客户端过滤、无分页；实体页变更轨迹窗口硬编码不可调。

## 1 本轮目标（v0.5.1：性能与体验优化，后端 API 零改动）

把 v0.5 交付时记录的"前端体积、分页、上限、硬编码"四类工程债清掉：首屏只加载所需模块、
异动页走服务端筛选与分页、报告证据表突破单次上限、变更轨迹窗口可调可深链。
全部改动限定在前端（apps/web）与文档；后端与 packages 不得改动。

## 2 功能范围（四项，每项独立可验证）

### 优化 A：路由级代码分割（首屏体积）

1. App.tsx 全部页面路由改 React.lazy + Suspense（壳内联中文加载态）；
2. echarts / cytoscape / china.json 等重组件随所属页面 chunk 按需加载；
3. vite 构建告警处理：如懒 chunk 仍超默认阈值，调整 chunkSizeWarningLimit 并注释理由；
4. 构建产物 before/after 逐 chunk 体积记录到 TEST_REPORT（before：单 JS 1,901.85KB /
   gzip 627.19KB）。

### 优化 B：报告证据收集分批

1. reportEvidence.ts：collectReportEvidence 改为分批调用 /evidence/lookup
   （每批 200 = 服务端上限，总上限提升至 1000 条声明）；
2. 抽 chunkIds 纯函数；批间合并证据映射；任一批失败整体降级为"无证据表"（维持现状语义）；
3. vitest：vi.mock api 验证分批次数、合并结果、总量截断与失败降级。

### 优化 C：异动页服务端筛选与分页

1. 事件类型筛选改为服务端参数（event_type），列表/总数以响应为准；
   类型 chips 展示全窗口 counts_by_type（标注"全窗口"）；
2. 新增"加载更多"（offset/limit 分页，页大小 100，items.length < total 时显示）；
3. eventsDisplay.ts 移除不再使用的客户端 filterEvents（及对应测试），保留 typeChips；
4. E2E 既有异动页断言（2→1→2）在服务端筛选下必须保持通过。

### 优化 D：实体页变更轨迹窗口可调

1. 变更轨迹区提供 from/to 日期选择（默认仍为 2022-01-01 → 2023-01-01），
   变更即刷新该区（不影响页面其余区块）；
2. 窗口写入 URL 查询参数（events_from/events_to，replace 导航），支持深链分享；
3. 窗口内无事件时显式空态（不再整区隐藏）。

## 3 硬约束

1. 后端（packages/、apps/api/、workers/、tests/ 后端部分）零改动；既有 179 项 pytest、
   42 项 vitest、16 项 E2E 全部保持绿色；
2. 每个推送提交必须 CI 绿：本轮全部改动单提交推送（吸取 v0.5 轮 0755b9c 中间提交红叉
   教训——不得把使测试通过的文件拆到后续提交）；推送前本地完整验证（pytest --cov /
   vitest / build / playwright / ruff）；
3. 界面中文、代码标识符英文；不新增任何前端/后端运行时依赖；
4. 文档同步：TEST_REPORT（§v0.5.1 优化记录，含构建体积 before/after 与实测命令）、
   DELIVERY（v0.5.1 小节）、USER_GUIDE（§8 加载更多与窗口可调说明）。
   未运行的事项不得标为完成。
5. 交付后推送 GitHub 并确认 CI 绿；最终回复列出：优化内容与位置 / 实测证据（含体积
   对比） / 已知限制与下一步建议。

## 4 实施顺序

阶段 A：完成路由级代码分割（App.tsx 已有半成品改动）→ build 记录体积 → vitest/build 绿。
阶段 B：优化 B（报告分批 + vitest）。阶段 C：优化 C（异动页分页 + eventsDisplay 清理）。
阶段 D：优化 D（变更轨迹窗口）。全部完成后跑全量验证（pytest --cov / vitest / build /
playwright / ruff）→ 文档 → 单提交 → 推送 → 确认 CI 绿。
```

中断续跑提示词：

```text
继续执行 CapitalGraph CN v0.5.1 性能与体验优化任务。先读 docs/TEST_REPORT.md §v0.5.1
与 git status，从第一个未完成的优化项继续；E2E 后端在 8301（seed=40，库
data/e2e-v05.sqlite3）。不要重复已通过工作、不要只汇报计划。本轮结束前更新文档并实际
运行 vitest/build/playwright 与后端 pytest --cov，单提交推送并确认 CI 绿。
```
