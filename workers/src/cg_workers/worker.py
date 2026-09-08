"""幂等采集 worker。

两种模式：
- once:   处理一个到期任务后退出（适合 cron/手动触发）
- loop:   常驻轮询，间隔可配

任务 kind：
- ingest_connector: 参数 {connector, params} → 运行 connector（幂等键防重）
- resolve_duplicates: 扫描同名实体生成解析候选与复核项

失败处理：指数退避（2^n 秒，封顶 10 分钟），超过 max_attempts 置 dead。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time

from cg_connectors.base import ConnectorContext
from cg_connectors.ingest import run_connector
from cg_connectors.registry import get_connector
from cg_domain.config import load_settings
from cg_domain.db import make_engine, make_session_factory
from cg_domain.enums import TaskStatus
from cg_domain.orm import Base
from cg_domain.repo import Repository
from cg_entity_resolution import ResolutionService


async def _ensure_schema(engine) -> None:
    # worker 可独立于 API 运行：启动时确保表存在（幂等）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def handle_task(session, kind: str, payload: dict) -> None:
    if kind == "ingest_connector":
        connector = get_connector(str(payload.get("connector", "")))
        if connector is None:
            raise RuntimeError(f"连接器不可用或已停用: {payload.get('connector')}")
        settings = load_settings()
        ctx = ConnectorContext(
            params={k: str(v) for k, v in (payload.get("params") or {}).items()},
            rate_limit_per_sec=settings.connector_rate_limit_per_sec,
            store_raw_documents=settings.store_raw_documents,
        )
        stats = await run_connector(session, connector, ctx)
        if stats is None:
            print("[worker] 幂等命中，跳过", flush=True)
        else:
            print("[worker] 采集完成:", json.dumps(stats.to_dict(), ensure_ascii=False), flush=True)
    elif kind == "resolve_duplicates":
        repo = Repository(session)
        from sqlalchemy import select

        from cg_domain.orm import Entity

        rows = (await session.execute(select(Entity.id).limit(500))).scalars().all()
        service = ResolutionService(session)
        candidates = 0
        for entity_id in rows:
            found = await service.find_candidates_for_entity(entity_id)
            candidates += len(found)
        await session.flush()
        print(f"[worker] 解析候选扫描完成: {candidates} 个候选/复核项", flush=True)
    else:
        raise RuntimeError(f"未知任务类型: {kind}")


async def run_once() -> int:
    settings = load_settings()
    engine = make_engine(settings.database_url)
    await _ensure_schema(engine)
    factory = make_session_factory(engine)
    processed = 0
    async with factory() as session:
        repo = Repository(session)
        task = await repo.claim_next_task()
        if task is None:
            print("[worker] 无到期任务", flush=True)
            await engine.dispose()
            return 0
        try:
            await handle_task(session, task.kind, json.loads(task.payload_json or "{}"))
            await repo.finish_task(task.id, ok=True)
            await session.commit()
            processed = 1
        except Exception as exc:  # noqa: BLE001 - 任务级失败隔离
            await repo.finish_task(task.id, ok=False, error=f"{type(exc).__name__}: {exc}")
            await session.commit()
            print(f"[worker] 任务失败({task.attempts}/{task.max_attempts}): {exc}", flush=True)
    await engine.dispose()
    return processed


async def run_loop(poll_interval: float) -> None:
    print(f"[worker] 常驻模式启动，轮询间隔 {poll_interval}s（Ctrl+C 退出）", flush=True)
    while True:
        processed = await run_once()
        if not processed:
            await asyncio.sleep(poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="CapitalGraph 采集 worker")
    parser.add_argument("--mode", choices=["once", "loop"], default="once")
    parser.add_argument("--interval", type=float, default=5.0, help="loop 模式轮询间隔(秒)")
    args = parser.parse_args()
    if args.mode == "once":
        asyncio.run(run_once())
    else:
        asyncio.run(run_loop(args.interval))


if __name__ == "__main__":
    main()
