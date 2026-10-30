# CapitalGraph API/worker 镜像（生产形态用）
FROM python:3.12-slim

# 安装 uv 作为包管理器
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages ./packages
COPY apps/api ./apps/api
COPY workers ./workers
COPY migrations ./migrations
COPY alembic.ini ./

# 前端构建产物由宿主预先构建后拷贝（避免在镜像内装 Node）
# COPY apps/web/dist ./web

RUN uv sync --frozen --no-dev

EXPOSE 8300
CMD ["uv", "run", "uvicorn", "cg_api.main:app", "--host", "0.0.0.0", "--port", "8300"]
