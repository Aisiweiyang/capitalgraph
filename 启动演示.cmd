@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 uv。请先安装：https://docs.astral.sh/uv/getting-started/installation/
  pause & exit /b 1
)

echo [1/4] 安装后端依赖（uv sync --frozen）...
uv sync --frozen
if errorlevel 1 ( echo 依赖安装失败 & pause & exit /b 1 )

echo [2/4] 数据库迁移...
uv run alembic upgrade head
if errorlevel 1 ( echo 迁移失败 & pause & exit /b 1 )

echo [3/4] 演示数据（已有数据会自动跳过）...
uv run cg-seed --entities 40

if not exist "apps\web\dist\index.html" (
  echo [错误] 未找到前端构建产物 apps\web\dist。
  echo 请先执行一次：  cd apps\web ^&^& npm install ^&^& npm run build
  pause & exit /b 1
)

echo [4/4] 启动服务（Ctrl+C 停止）...
echo.
echo    打开浏览器访问:  http://127.0.0.1:8300
echo    演示账号:  viewer / viewer-demo-password   （admin 见 README）
echo    若提示端口被占用:  把下方 8300 改成 8301 等其他端口即可
echo.
set CG_WEB_DIST=apps/web/dist
uv run uvicorn cg_api.main:app --port 8300
pause
