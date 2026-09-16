"""运营仓储：审计日志（只追加）、复核队列、质量标记、任务、用户。

安全约束：AuditLog 与 QualityIssue 不提供更新/删除方法；
复核解决只能写 ReviewItem 的状态字段，原始记录保留。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cg_domain.enums import ReviewStatus, Role, TaskStatus
from cg_domain.orm import (
    AuditLog,
    QualityIssue,
    ReviewItem,
    RiskFlag,
    Task,
    User,
)


class OpsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------- 审计

    async def audit(
        self,
        *,
        actor: str,
        action: str,
        target: str = "",
        request_id: str = "",
        result: str = "ok",
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                actor=actor[:64],
                action=action[:64],
                target=target[:128],
                request_id=request_id[:64],
                result=result[:16],
                detail_json=json.dumps(detail or {}, ensure_ascii=False, default=str),
            )
        )
        await self.session.flush()

    async def audit_tail(self, limit: int = 100) -> list[AuditLog]:
        rows = await self.session.execute(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    # ------------------------------------------------------------- 复核队列

    async def add_review_item(
        self, kind: str, payload: dict[str, Any], *, assignee: str | None = None
    ) -> ReviewItem:
        item = ReviewItem(
            kind=kind,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            assignee=assignee,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_review_items(
        self, status: str | None = None, limit: int = 100
    ) -> list[ReviewItem]:
        stmt = select(ReviewItem).order_by(ReviewItem.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(ReviewItem.status == status)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def resolve_review_item(self, item_id: str, note: str, actor: str) -> ReviewItem | None:
        item = await self.session.get(ReviewItem, item_id)
        if item is None:
            return None
        item.status = ReviewStatus.RESOLVED.value
        item.resolution_note = note
        item.assignee = actor
        item.resolved_at = datetime.now(UTC)
        await self.session.flush()
        return item

    # ------------------------------------------------------------- 质量与风险

    async def add_quality_issue(
        self,
        rule_name: str,
        *,
        severity: str = "warning",
        entity_id: str | None = None,
        statement_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> QualityIssue:
        issue = QualityIssue(
            rule_name=rule_name,
            severity=severity,
            entity_id=entity_id,
            statement_id=statement_id,
            detail_json=json.dumps(detail or {}, ensure_ascii=False, default=str),
        )
        self.session.add(issue)
        await self.session.flush()
        return issue

    async def open_quality_issue(self, rule_name: str, statement_id: str) -> QualityIssue | None:
        """同规则同声明的 open 标记（扫描类规则幂等入库的去重依据）。"""
        row = await self.session.execute(
            select(QualityIssue)
            .where(
                QualityIssue.rule_name == rule_name,
                QualityIssue.statement_id == statement_id,
                QualityIssue.status == "open",
            )
            .limit(1)
        )
        return row.scalars().first()

    async def add_risk_flag(
        self,
        flag_type: str,
        *,
        subject_entity_id: str | None = None,
        subject_statement_id: str | None = None,
        calculation_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RiskFlag:
        flag = RiskFlag(
            flag_type=flag_type,
            subject_entity_id=subject_entity_id,
            subject_statement_id=subject_statement_id,
            calculation_id=calculation_id,
            payload_json=json.dumps(payload or {}, ensure_ascii=False, default=str),
        )
        self.session.add(flag)
        await self.session.flush()
        return flag

    async def list_risk_flags(
        self, *, flag_types: tuple[str, ...] | None = None, limit: int = 200
    ) -> list[RiskFlag]:
        """最近产生的风险标记（算法候选，只读展示）。"""
        stmt = select(RiskFlag).order_by(RiskFlag.created_at.desc()).limit(limit)
        if flag_types:
            stmt = stmt.where(RiskFlag.flag_type.in_(list(flag_types)))
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def open_risk_flag_subjects(self, flag_types: tuple[str, ...] | None = None) -> list[str]:
        """status=open 的风险标记涉及的去重主体（传导口径："出险"=被标 RiskFlag）。"""
        stmt = (
            select(RiskFlag.subject_entity_id)
            .where(
                RiskFlag.status == "open",
                RiskFlag.subject_entity_id.is_not(None),
            )
            .distinct()
        )
        if flag_types:
            stmt = stmt.where(RiskFlag.flag_type.in_(list(flag_types)))
        rows = await self.session.execute(stmt)
        return [r for r in rows.scalars().all() if r]

    # ------------------------------------------------------------- 任务

    async def enqueue_task(
        self, kind: str, idempotency_key: str, payload: dict[str, Any], *, max_attempts: int = 5
    ) -> Task | None:
        """幂等入队：同键任务已存在返回 None。"""
        existing = await self.session.execute(
            select(Task.id).where(Task.idempotency_key == idempotency_key).limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            return None
        task = Task(
            kind=kind,
            idempotency_key=idempotency_key,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            max_attempts=max_attempts,
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def claim_next_task(self) -> Task | None:
        """领取一个到期任务（简单乐观锁：状态 pending → running）。"""
        now = datetime.now(UTC)
        row = await self.session.execute(
            select(Task)
            .where(
                Task.status == TaskStatus.PENDING.value,
                or_(Task.next_retry_at.is_(None), Task.next_retry_at <= now),
            )
            .order_by(Task.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        task = row.scalars().first()
        if task is None:
            return None
        task.status = TaskStatus.RUNNING.value
        task.attempts += 1
        await self.session.flush()
        return task

    async def finish_task(self, task_id: str, ok: bool, error: str = "") -> Task | None:
        task = await self.session.get(Task, task_id)
        if task is None:
            return None
        if ok:
            task.status = TaskStatus.SUCCEEDED.value
            task.last_error = ""
        else:
            error_tail = (error or "")[:1000]
            if task.attempts >= task.max_attempts:
                task.status = TaskStatus.DEAD.value
                task.last_error = error_tail
            else:
                # 指数退避：2^n 秒，封顶 10 分钟
                delay = min(2**task.attempts, 600)
                task.status = TaskStatus.PENDING.value
                task.last_error = error_tail
                task.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
        await self.session.flush()
        return task

    # ------------------------------------------------------------- 用户与 RBAC

    async def get_user_by_username(self, username: str) -> User | None:
        row = await self.session.execute(select(User).where(User.username == username).limit(1))
        return row.scalars().first()

    async def create_user(self, username: str, password_hash: str, role: Role) -> User:
        user = User(username=username, password_hash=password_hash, role=role.value)
        self.session.add(user)
        await self.session.flush()
        return user

    async def user_count(self) -> int:
        # 注意：await 必须先于 .scalar_one()——协程对象没有该方法（曾被 mypy 揪出）
        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar_one())
