# ZCode 提示词归档：v0.6 证据质量与覆盖率趋势

> 驱动 v0.6（证据质量治理层：覆盖率趋势与时效提示）交付的需求侧原始提示词，
> 基线 ffc4df4（v0.5.1 归档提交）。归档惯例见 DELIVERY.md §提示词归档。

```text
继续执行 CapitalGraph CN v0.6 证据质量与覆盖率趋势任务（基线 ffc4df4，工作区已有大量
未提交改动）。先读 docs/PROJECT_PLAN.md、docs/DECISIONS.md、docs/TEST_REPORT.md 与
git log / git status，运行 uv run pytest tests -q 与 uv run python scripts/module_graph.py
做最小状态检查，再从第一个未完成的验收项继续。

当前进度（上一轮中断点）：
- 已完成并验证：切片 A（coverage_timeline 纯函数 6 测 + GET /evidence/coverage/timeline
  3 测 + 前端趋势区/vitest 4 测）、切片 B（EvidenceRecord.captured_at 数据链路、
  synthetic 质押证据回填 2019-01-01、stale_evidence 纯函数 6 测、repo max(fetched_at)
  2 测、GET /evidence/staleness 与 POST /staleness/scan 幂等 6 测、前端时效区/vitest）；
  中断前全量后端 202 passed 零回归、前端 vitest 54 passed。
- 切片 C 代码已写完但未验证：report.ts（staleCapturedAt/快照时间列/陈旧标注/覆盖率摘要行）、
  reportEvidence.ts（collectReportEvidence 增 opts + collectCoverageSummary）、
  Explore/Families/Flows 四处导出已接通、report.test.ts 新增 4 测、EvidenceFragment 增
  fetched_at 字段。
- 已知阻塞：apps/web/src/pages/Flows.tsx 第 438 行附近 tsc 报 TS1005（导出按钮改成
  async 块后括号未闭合），先修复；随后跑 cd apps/web && npx tsc -b && npx vitest run
  验证切片 C（report.test.ts 新用例：边界恰好 N 年不算陈旧/快照列/陈旧标注/覆盖率行/降级不显示）。

剩余工作：
1. 切片 D：Playwright 新用例（趋势区渲染、时效区空态/列表、viewer 视角 scan 按钮 RBAC 提示，
   既有 16 项不得回归；E2E 后端按惯例在 8301 起种子库 data/e2e-v05.sqlite3，需重建以含
   captured_at 回填）；性能基线 tests/performance/test_v06_perf.py（2008 声明规模
   /evidence/coverage/timeline 与 /evidence/staleness，仿 test_v05_perf.py）。
2. 文档：ADR-019（覆盖率趋势口径）、ADR-020（时效规则口径——仅提示不认定，引 ISO/IEC 25012
   Currentness 与 SodaCL freshness 同族规则、Great Expectations/Soda Core/Deequ 不引入结论）、
   ARCHITECTURE/DATA_MODEL 增量、OSS_EVALUATION v0.6 增量（GX Apache-2.0 2026-09-10 发版、
   Soda Core 4.18.0、Deequ 2.0.14-spark-4.0 均核实）、USER_GUIDE/TEST_REPORT（实际命令与
   结果）/DELIVERY/README、PROJECT_PLAN v0.6 验收清单；本提示词归档 docs/prompts/。
3. 全量验证（pytest --cov / vitest / build / playwright / ruff / module_graph / secret_scan）
   → 单提交推送 → 确认 CI 绿。提交信息沿仓库惯例（feat: v0.6 —— 证据质量治理层：…），
   代码注释与提交信息按既有工程风格收敛，不加模板化尾注。

不要重新初始化、不要重复已通过工作、不要只汇报计划；本轮结束前更新文档并实际运行相关测试。
```
