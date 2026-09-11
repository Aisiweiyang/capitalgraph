# 迁移指南（MIGRATION）

本文回答两个问题：**整个项目如何搬到新机器/新路径**，以及**单个模块如何被独立抽取复用**。
模块化迁移的前提由 ADR-001（uv workspace）、ADR-010（自包含子目录）与 `scripts/module_graph.py`（边界强制）共同保证。

## 1. 整体迁移（换机器 / 换路径 / 换数据库）

仓库自包含：所有第三方依赖锁定在 `uv.lock` 与 `apps/web/package-lock.json`，无绝对路径引用。

```bash
# 1) 复制目录（或 git clone）；中文路径可用，但建议 ASCII 路径以规避个别工具的编码问题
git clone <repo-url> CapitalGraph && cd CapitalGraph
# 或者直接复制整个目录，Git 历史随目录走

# 2) 后端（uv 自动管理 Python 3.12）
uv sync                      # 按 uv.lock 精确还原依赖
uv run alembic upgrade head  # 建表（目标库由 CG_DATABASE_URL 决定）

# 3) 前端
cd apps/web && npm ci && npm run build && cd ../..

# 4) 种子 + 启动
uv run cg-seed --entities 40
CG_WEB_DIST=apps/web/dist uv run uvicorn cg_api.main:app --port 8300
```

### 数据库迁移矩阵

| 场景 | 做法 |
| --- | --- |
| SQLite → SQLite | 直接复制 `data/*.sqlite3` 文件（先停服务） |
| SQLite → PostgreSQL | `CG_DATABASE_URL=postgresql+asyncpg://...` 后 `alembic upgrade head`，再用 CSV 导出/连接器重放数据 |
| 新版本升级 | `git pull && uv sync && uv run alembic upgrade head`（迁移双方言兼容，upgrade/downgrade 回环有测试） |

### 环境变量清单（全部可缺省）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `CG_DATABASE_URL` | `sqlite+aiosqlite:///./data/capitalgraph.sqlite3` | 单一事实源连接串 |
| `CG_SECRET_KEY` | 演示默认值 | JWT 签名密钥；生产必设 |
| `CG_WEB_DIST` | 自动探测 `apps/web/dist` | 前端静态产物目录 |
| `CG_CORS_ORIGINS` | `http://localhost:5173,...` | 开发期跨域白名单 |
| `CG_STORE_RAW_DOCUMENTS` | `true` | 合规开关：关闭后只存哈希与链接 |

### 数据备份与恢复

`scripts/backup.sh` 打包数据库与对象存储；恢复演练步骤见 `docs/TEST_REPORT.md`。
`data/`、`backups/` 均在 `.gitignore` 内，不随仓库迁移，需单独传输。

## 2. 单模块抽取（模块化复用）

每个 Python 包都是独立 uv 项目（自带 `pyproject.toml`、`hatchling` 构建、语义化依赖声明），
发布到私有 PyPI 或以 git 依赖方式单独引用即可。边界由 CI 运行
`uv run python scripts/module_graph.py` 强制：**任何未声明的内部依赖会直接失败**。

| 模块 | 对外接口 | 抽取方式 |
| --- | --- | --- |
| `cg-domain` | ORM 模型、`Repository`、规范化、搜索接口 | 零内部依赖，直接引用；可选 extra：`[postgres]`、`[sqlite]` |
| `cg-capital-graph` | `engine`（路径遍历）、`analysis`（聚合/UBO/环路/交叉持股） | 纯函数，输入为声明边集合；只依赖 cg-domain 类型 |
| `cg-entity-resolution` | `ResolutionService`、评分与决策记录 | 依赖 cg-domain |
| `cg-connectors` | `Connector` 协议、运行器、内容寻址对象存储、合成数据源 | 依赖 cg-domain；可选 extra：`[http]` |
| `apps/web` | 独立 npm 工程 | `npm ci` 后可脱离后端开发（`/api` 代理到 8300） |

抽取示例：

```bash
# 把穿透算法作为独立库引用（私有 Git 示例）
uv add "cg-capital-graph @ git+https://example.internal/capitalgraph.git@v0.1.0#subdirectory=packages/capital_graph"
```

### 迁移守门检查

```bash
uv run python scripts/module_graph.py   # 边界：实际导入 ⊆ 声明依赖
uv run pytest tests                     # 行为：66 项测试
git grep -n "from cg_" -- apps api packages workers  # 人工复核跨模块引用
```

## 3. 前端后端分离部署

后端可独立服务前端：`CG_WEB_DIST=apps/web/dist uv run uvicorn cg_api.main:app`（单进程）。
也可完全分离：前端产物部署到任意静态服务器，构建时通过 Vite 代理或反向代理把 `/api`
指向 API 服务；鉴权为无状态 JWT，无需会话粘滞。
