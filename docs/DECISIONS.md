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
- 决策：CapitalGraph CN 全部成果收敛于 `capitalgraph/` 子目录，内含独立 Git 仓库、独立 uv workspace、
  独立 npm 工程；绝不读写父目录中 asg-* 相关文件。
- 代价：父目录与本项目各有仓库，需分别操作；收益：零冲突，`capitalgraph/` 整体可搬移到任意路径。
- 提示词中"当前目录"解释为本项目子目录；最终交付物均位于 `capitalgraph/` 内。
