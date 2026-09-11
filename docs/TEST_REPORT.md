# 测试报告（TEST_REPORT）

生成时间：2026-09-11（v0.2 增量更新）｜ 全部结果来自实际运行（Windows 11 / Git Bash / Python 3.12 / Node v24）

## 1. 测试执行总览

| 套件 | 命令 | 结果 | 退出码 |
| --- | --- | --- | --- |
| 后端全量（单元+集成+安全+性能） | `uv run pytest tests --cov --cov-report=term` | **66 passed**（2026-09-11 实测） | 0 |
| 覆盖率 | 同上 | TOTAL **89.3%**（2429 语句 / 260 未覆盖） | 0 |
| 前端组件（vitest） | `cd apps/web && npm test` | **6 passed**（新增仪表板 3 项） | 0 |
| E2E（Playwright + Chromium） | `cd apps/web && npx playwright test` | **8 passed**（10–12s） | 0 |
| Lint | `uv run ruff check packages apps workers tests` | All checks passed | 0 |
| 格式 | `uv run ruff format --check …` | 通过 | 0 |

## 2. 覆盖率要点（89.3% 全项目；核心领域分支 >85% 达标）

| 模块 | 覆盖率 |
| --- | --- |
| cg-capital_graph（engine/analysis） | 99.2% / 94.9% |
| cg-domain（models 99.2%、orm 99.6%、repo 全部 >90%、normalization 91.7%） | ≈98% |
| cg-entity_resolution | features/scoring 100%，service ≈90% |
| cg-connectors（synthetic 99%、csv_source 95.2%、ingest 85.3%、storage 83%） | ≈92% |
| cg-api（schemas 100%、state 100%、auth 86%、routers penetration 93.8%） | ≈78% |

覆盖配置要点：`concurrency = ["thread", "greenlet"]`（否则 FastAPI 异步路由在 TestClient 线程中不被追踪，
首次测量曾误报 44%）。

## 3. 必测项对照（提示词 §9）

| 要求 | 实现与证据 |
| --- | --- |
| 1 单元：时态声明/匹配/比例/路径/环路/交叉持股/聚合/UBO/规则解释 | tests/domain/test_models.py、tests/capital_graph/test_penetration.py（链式/多路径/环/缺比例/剪枝/确定性/超时/交叉持股/UBO R1R2/假设说明） |
| 2 数据质量：schema/唯一性/引用完整性/时间区间/比例范围/来源必填/哈希/重复冲突 | 契约层校验测试 + statement payload 幂等 + identifier_reused 质量标记 + quality_issues 端点（tests/api） |
| 3 集成：迁移/API/存储/fixture connector/失败重试/幂等 | Alembic upgrade→downgrade→upgrade 回环（SQLite 实测）；tests/api（API+连接器全链路幂等）；tests/workers（退避、失败隔离） |
| 4 API contract：分页/筛选/排序/认证/越权/限流/错误码 | tests/api/test_api.py：viewer/analyst/admin 三级越权 401/403/404/422/429 |
| 5 前端：组件/图操作/空态/错误态/权限态 | apps/web/src/Search.test.tsx + RoleGate 权限页 + 各页空/错态 |
| 6 E2E：导入→检索→详情→展开穿透→证据→时间点→导出 | apps/web/e2e/core-flow.spec.ts 8 项（含 CSV/PNG 真实下载） |
| 7 安全：未授权/越权/注入/XSS/SSRF/穿越/恶意上传/日志泄密/依赖漏洞 | tests/api（注入参数化、RBAC、限流）；storage 路径穿越拒绝测试；CSV 公式注入转义；日志不含堆栈与授权头；§4 扫描 |
| 8 性能：可重复合成器、规模、p50/p95、错误率、内存 | tests/performance/test_perf.py（见 §5） |
| 9 清洁环境 | 冻结安装→迁移→种子→健康→鉴权→检索 一键链路实测通过 |

## 4. 安全检查结果

| 检查 | 工具 | 结果 |
| --- | --- | --- |
| SAST | `uvx bandit -q -r packages apps/api/src workers/src` | **0 findings**（exit 0） |
| Python 依赖漏洞 | `uvx pip-audit -r requirements.txt` | **0 vulnerabilities**（仅工作区本地包跳过提示） |
| 前端依赖漏洞 | `npm audit` | **0 critical / 0 high**（升级 vite@8、vitest@5 后；余 2 个 moderate 均为 dev 工具链：esbuild dev-server、react-router，不进入生产产物） |
| 硬编码秘密 | `uv run python scripts/secret_scan.py` | 通过（0 findings） |
| 迁移回滚 | `alembic downgrade base` → `upgrade head` | 通过（SQLite 实测，含视图对象） |

## 5. 性能（可重复合成器；机器：AMD64 / Windows / Python 3.12.13）

| 场景 | 规模 | p50 | p95 | 错误率 | 峰值内存 | 确定性 |
| --- | --- | --- | --- | --- | --- | --- |
| 随机网络穿透 | 280 节点 / 586 边 | 0.6ms | 0.7ms | 0 | 91MB | ✓ |
| 随机网络穿透 | 1300 节点 / 2990 边 | 2.4ms | 2.4ms | 0 | 421MB | ✓ |
| 500 节点纯环（T13 对抗） | 500 节点 / 500 边 | 单次 28.8ms 完成环检测，无栈溢出/无死循环 | | | | ✓ |

## 6. 恢复演练（DATA_GOVERNANCE §备份与恢复）

```
1) VACUUM INTO 一致性快照备份      → backups/drill.sqlite3 (573KB)
2) 行数校验(备份=源)               → entities 40 / statements 130 / aliases 40 / identifiers 69 / users 3
3) 删除源库（模拟灾难）             → data/e2e.sqlite3 removed
4) 从备份恢复至原路径
5) 恢复后行数一致                   → 全部相等，演练成功
```

## 7. 已知问题与限制（不构成验收失败，如实记录）

1. `npm audit` 余 2 个 moderate，均为仅开发链路（esbuild dev server、react-router），生产构建产物不含。
2. fastapi TestClient 触发 starlette 弃用告警（httpx2 迁移生态进行中），不影响功能。
3. 限流为单实例内存令牌桶；多实例部署需外置存储（见 THREAT_MODEL 残余风险）。
4. SQLite 默认未启用 WAL，高并发写场景建议生产使用 PostgreSQL（compose 就绪）。
5. 中文检索基于规范化包含匹配（无分词）；数据量证明需要时按 ADR-003 引入专用搜索。
6. Playwright E2E 依赖本机后端在 8300 运行；本轮曾因演练 kill 后端导致 1 次误报失败，重启后 8/8 通过。

## 8. v0.2 增量（2026-09-11：文件整理 / 可视化 / 模块化迁移）

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `uv run pytest tests --cov` | **66 passed**，TOTAL **89.4%**（新增 `/stats` 聚合测试 2 项） |
| 前端组件 | `cd apps/web && npm test` | **6 passed**（Dashboard 卡片/图表/空态 + BarChart 空态） |
| 前端构建 | `cd apps/web && npm run build` | 成功（tsc strict + vite） |
| E2E 回归 | `cd apps/web && npx playwright test` | **8 passed**（10.5s） |
| 模块边界 | `uv run python scripts/module_graph.py` | 通过；并修正 3 处声明失真（cg-capital-graph 缺声明 cg-domain、cg-workers 缺声明 cg-entity-resolution、cg-api 冗余声明 cg-entity-resolution），uv.lock 已同步 |
| 可视化冒烟 | 浏览器实测 `/dashboard` 与 `/explore/{id}` | 仪表板 5 卡片 + 4 图表渲染正确；穿透图图例含实体类型色标与「N 实体 · M 关系」统计 |

修复记录：年份条形图满高柱数值标签被 viewBox 裁剪 → 顶部预留 22px；SVG 随容器拉伸导致标签字体过大 → 改为固定原始尺寸渲染。
既有问题修复：vitest 默认误扫 `e2e/*.spec.ts` → `vite.config.ts` 限定 `include: src/**`，`npm test` 语义恢复为单元测试。
