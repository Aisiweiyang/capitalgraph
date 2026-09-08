"""worker 测试：任务入队/领取/退避/失败隔离 + 解析候选扫描。"""

import json

from cg_domain.enums import Role
from cg_domain.repo import Repository
from cg_domain.orm import Entity
from cg_workers.worker import handle_task, run_once


async def test_ingest_task_via_worker(db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("CG_STORE_RAW_DOCUMENTS", "false")
    repo = Repository(db_session)
    task = await repo.enqueue_task(
        "ingest_connector",
        "worker-test-1",
        {"connector": "synthetic", "params": {"seed": "7", "entities": "6"}},
    )
    await handle_task(db_session, "ingest_connector", json.loads(task.payload_json))
    await repo.finish_task(task.id, ok=True)
    assert task.status == "succeeded"
    hits_total = (await repo.search("公司"))[1]
    assert hits_total > 0


async def test_unknown_task_kind_fails_isolated(db_session):
    repo = Repository(db_session)
    task = await repo.enqueue_task("bogus_kind", "worker-test-2", {})
    import pytest

    with pytest.raises(RuntimeError, match="未知任务类型"):
        await handle_task(db_session, "bogus_kind", {})
    await repo.finish_task(task.id, ok=False, error="未知任务类型: bogus_kind")
    assert task.status == "pending"  # 未达上限，等待退避重试
    assert task.attempts == 0  # handle_task 内不计数，claim 时计数


async def test_resolve_duplicates_creates_review_items(db_session):
    repo = Repository(db_session)
    # 两个同名实体（一个带 USCC、一个不带）→ 疑似重复候选
    for ext, uscc in (("D1", "91110000ABCDEF01X9"), ("D2", None)):
        await repo.upsert(_make_record(ext, uscc))
    await handle_task(db_session, "resolve_duplicates", {})
    items = await repo.list_review_items()
    assert any(i.kind == "suspected_duplicate" for i in items)


def _make_record(ext: str, uscc: str | None):
    from cg_domain.models import EntityRecord

    return EntityRecord(
        connector_id="synthetic", external_id=ext, name="同名测试有限公司", uscc=uscc
    )


async def test_run_once_with_no_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "CG_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/worker.sqlite3"
    )
    assert await run_once() == 0
