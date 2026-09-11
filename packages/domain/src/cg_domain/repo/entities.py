"""实体仓储：标识符优先的实体 upsert、检索与详情。

规则：只按标识符（uscc/lei/ticker/来源内部键）匹配既有实体；
名称仅生成规范化字段供检索与相似候选，绝不作为合并依据。
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cg_domain.enums import AliasType, EntityKind
from cg_domain.models import EntityRecord
from cg_domain.normalization import normalize_name
from cg_domain.orm import Entity, EntityIdentifier, NameAlias, Security, Statement


class EntityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_id_by_identifier(self, namespace: str, value: str) -> str | None:
        row = await self.session.execute(
            select(EntityIdentifier.entity_id)
            .where(EntityIdentifier.namespace == namespace, EntityIdentifier.value == value)
            .limit(1)
        )
        return row.scalar_one_or_none()

    async def get(self, entity_id: str) -> Entity | None:
        return await self.session.get(Entity, entity_id)

    async def create(self, record: EntityRecord) -> Entity:
        entity = Entity(
            kind=record.kind.value,
            primary_name=record.name,
            primary_norm_name=record.norm_name,
            region_code=record.region_code,
            industry=record.industry,
        )
        self.session.add(entity)
        await self.session.flush()
        await self.add_alias(
            entity.id, record.name, AliasType.OFFICIAL, valid_from=record.valid_from
        )
        for former in record.former_names:
            await self.add_alias(entity.id, former, AliasType.FORMER, valid_from=record.valid_from)
        await self.add_identifier(entity.id, "src", f"{record.connector_id}:{record.external_id}")
        if record.uscc:
            await self.add_identifier(entity.id, "uscc", record.uscc.upper())
        if record.lei:
            await self.add_identifier(entity.id, "lei", record.lei.upper())
        if record.ticker and record.exchange:
            await self.add_identifier(entity.id, f"ticker:{record.exchange}", record.ticker)
            self.session.add(
                Security(
                    entity_id=entity.id,
                    code=record.ticker,
                    exchange=record.exchange,
                    security_type="stock",
                )
            )
        await self.session.flush()
        return entity

    async def add_identifier(self, entity_id: str, namespace: str, value: str) -> None:
        exists = await self.find_id_by_identifier(namespace, value)
        if exists == entity_id:
            return
        if exists is not None:
            # 同一标识符挂在不同实体：不自动合并，入库为重复候选由复核处理。
            from cg_domain.orm import QualityIssue

            self.session.add(
                QualityIssue(
                    rule_name="identifier_reused",
                    severity="warning",
                    entity_id=entity_id,
                    detail_json=(
                        f'{{"namespace": "{namespace}", "value": "{value}", '
                        f'"other_entity_id": "{exists}"}}'
                    ),
                )
            )
            return
        self.session.add(EntityIdentifier(entity_id=entity_id, namespace=namespace, value=value))
        await self.session.flush()

    async def add_alias(
        self,
        entity_id: str,
        name: str,
        alias_type: AliasType,
        *,
        lang: str = "zh",
        valid_from=None,
        valid_to=None,
    ) -> None:
        normalized = normalize_name(name)
        row = await self.session.execute(
            select(NameAlias.id)
            .where(
                NameAlias.entity_id == entity_id,
                NameAlias.norm_name == normalized,
                NameAlias.alias_type == alias_type.value,
            )
            .limit(1)
        )
        if row.scalar_one_or_none() is not None:
            return
        self.session.add(
            NameAlias(
                entity_id=entity_id,
                name=name,
                norm_name=normalized,
                alias_type=alias_type.value,
                lang=lang,
                valid_from=valid_from,
                valid_to=valid_to,
            )
        )
        await self.session.flush()

    async def upsert(self, record: EntityRecord) -> Entity:
        """标识符优先解析；命中即复用实体，未命中创建新实体。"""
        for namespace, value in (
            ("uscc", record.uscc.upper() if record.uscc else None),
            ("lei", record.lei.upper() if record.lei else None),
            ("src", f"{record.connector_id}:{record.external_id}"),
        ):
            if not value:
                continue
            found = await self.find_id_by_identifier(namespace, value)
            if found:
                entity = await self.get(found)
                if entity is None:
                    # 标识符索引命中但实体已不存在（不一致/竞态）：跳过陈旧索引继续创建
                    continue
                if record.former_names:
                    for former in record.former_names:
                        await self.add_alias(
                            entity.id, former, AliasType.FORMER, valid_from=record.valid_from
                        )
                return entity
        return await self.create(record)

    async def search(
        self,
        query: str,
        *,
        kinds: list[EntityKind] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Entity], int]:
        """规范化名称包含匹配 + 标识符精确匹配。返回 (hits, total)。"""
        normalized = normalize_name(query)
        stmt = select(Entity)
        conditions = [
            or_(
                Entity.primary_norm_name.contains(normalized),
                Entity.primary_name.contains(query),
            )
        ]
        if kinds:
            conditions.append(Entity.kind.in_([k.value for k in kinds]))
        stmt = stmt.where(*conditions)
        total = (
            await self.session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Entity.primary_norm_name).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), int(total)

    async def search_by_identifier(self, query: str, limit: int = 20) -> list[Entity]:
        stmt = (
            select(Entity)
            .join(EntityIdentifier, EntityIdentifier.entity_id == Entity.id)
            .where(EntityIdentifier.value.contains(query.upper()))
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def aliases(self, entity_id: str) -> list[NameAlias]:
        rows = await self.session.execute(
            select(NameAlias).where(NameAlias.entity_id == entity_id).order_by(NameAlias.name)
        )
        return list(rows.scalars().all())

    async def identifiers(self, entity_id: str) -> list[EntityIdentifier]:
        rows = await self.session.execute(
            select(EntityIdentifier)
            .where(EntityIdentifier.entity_id == entity_id)
            .order_by(EntityIdentifier.namespace, EntityIdentifier.value)
        )
        return list(rows.scalars().all())

    async def securities(self, entity_id: str) -> list[Security]:
        rows = await self.session.execute(select(Security).where(Security.entity_id == entity_id))
        return list(rows.scalars().all())

    async def neighbours(self, entity_id: str) -> dict[str, list[Statement]]:
        """当前有效（status=active）的一跳关系，按方向分组。"""
        incoming = (
            (
                await self.session.execute(
                    select(Statement).where(
                        Statement.object_id == entity_id, Statement.status == "active"
                    )
                )
            )
            .scalars()
            .all()
        )
        outgoing = (
            (
                await self.session.execute(
                    select(Statement).where(
                        Statement.subject_id == entity_id, Statement.status == "active"
                    )
                )
            )
            .scalars()
            .all()
        )
        return {"incoming": list(incoming), "outgoing": list(outgoing)}
