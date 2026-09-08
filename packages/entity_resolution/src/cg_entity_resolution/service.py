"""解析服务：候选发现、决策落档、合并执行。

候选生成范围（当前实现）：同名/近名实体对。更大规模需要阻塞索引（LSH），
触发条件记录在 docs/PROJECT_PLAN.md 的扩展项。
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cg_domain.enums import DecisionBy, DecisionOutcome
from cg_domain.normalization import normalize_name
from cg_domain.orm import (
    Entity,
    EntityIdentifier,
    ResolutionCandidate,
    ResolutionDecision,
    ReviewItem,
)
from cg_entity_resolution.features import PairFeatures, compute_features
from cg_entity_resolution.scoring import (
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    METHOD,
    METHOD_VERSION,
    ScoredPair,
    score_pair,
)

_METHOD_SIGNATURE = json.dumps(
    {
        "weights": DEFAULT_WEIGHTS.__dict__,
        "thresholds": DEFAULT_THRESHOLDS.__dict__,
        "method": METHOD,
    },
    sort_keys=True,
)
_INPUT_HASH = hashlib.sha256(_METHOD_SIGNATURE.encode("utf-8")).hexdigest()


class ResolutionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load_identifiers(self, entity_ids: list[str]) -> list[EntityIdentifier]:
        if not entity_ids:
            return []
        rows = await self.session.execute(
            select(EntityIdentifier).where(EntityIdentifier.entity_id.in_(entity_ids))
        )
        return list(rows.scalars().all())

    async def score_existing_pair(
        self, left: Entity, right: Entity
    ) -> tuple[PairFeatures, ScoredPair]:
        id_rows = await self._load_identifiers([left.id, right.id])
        features = compute_features(left, right, id_rows, id_rows)
        return features, score_pair(features)

    async def find_candidates_for_entity(self, entity_id: str, *, limit: int = 20) -> list[ResolutionCandidate]:
        """对给定实体生成解析候选（同规范名或后缀剥离名一致的其它实体）。"""
        entity = await self.session.get(Entity, entity_id)
        if entity is None:
            return []
        norm = normalize_name(entity.primary_name)
        rows = (
            (
                await self.session.execute(
                    select(Entity)
                    .where(Entity.primary_norm_name == norm, Entity.id != entity_id)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        candidates: list[ResolutionCandidate] = []
        for other in rows:
            features, scored = await self.score_existing_pair(entity, other)
            if scored.suggested == "none":
                continue
            candidate = ResolutionCandidate(
                entity_id_left=entity.id,
                entity_id_right=other.id,
                features_json=json.dumps(features.to_dict(), ensure_ascii=False),
                score=scored.score,
                threshold=DEFAULT_THRESHOLDS.review_band,
                method=METHOD,
                method_version=METHOD_VERSION,
                input_hash=_INPUT_HASH,
            )
            self.session.add(candidate)
            await self.session.flush()
            await self._attach_auto_decision(candidate, scored)
            candidates.append(candidate)
        return candidates

    async def _attach_auto_decision(self, candidate: ResolutionCandidate, scored: ScoredPair) -> None:
        if scored.suggested == "merge":
            decision_outcome = DecisionOutcome.MERGE
            decided_by = DecisionBy.RULE
        elif scored.suggested == "review":
            decision_outcome = DecisionOutcome.PENDING
            decided_by = DecisionBy.RULE  # 规则只建议进入复核，不做合并
        else:
            return
        decision = ResolutionDecision(
            candidate_id=candidate.id,
            decision=decision_outcome.value,
            decided_by=decided_by.value,
            reason="；".join(scored.reasons),
            actor="system",
        )
        self.session.add(decision)
        await self.session.flush()
        if decided_by is DecisionBy.RULE and decision_outcome is DecisionOutcome.PENDING:
            self.session.add(
                ReviewItem(
                    kind="suspected_duplicate",
                    payload_json=json.dumps(
                        {
                            "candidate_id": candidate.id,
                            "left_id": candidate.entity_id_left,
                            "right_id": candidate.entity_id_right,
                            "score": candidate.score,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            await self.session.flush()

    async def decide(
        self,
        candidate_id: str,
        outcome: DecisionOutcome,
        *,
        actor: str,
        reason: str,
        by: DecisionBy = DecisionBy.HUMAN,
    ) -> ResolutionDecision:
        decision = ResolutionDecision(
            candidate_id=candidate_id,
            decision=outcome.value,
            decided_by=by.value,
            reason=reason,
            actor=actor,
        )
        self.session.add(decision)
        await self.session.flush()
        return decision


async def apply_merge(
    session: AsyncSession, source_id: str, target_id: str, *, actor: str
) -> Entity:
    """把 source 合并进 target：source.merged_into_id = target。

    不物理删除、不改写历史声明；API 层读取实体时透明重定向。
    """
    source = await session.get(Entity, source_id)
    target = await session.get(Entity, target_id)
    if source is None or target is None:
        raise ValueError("待合并实体不存在")
    if source_id == target_id:
        raise ValueError("不能合并到自身")
    source.merged_into_id = target_id
    await session.flush()
    return source
