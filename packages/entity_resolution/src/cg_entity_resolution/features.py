"""实体对特征：用于解释“为什么像同一个主体”。全部特征可 JSON 序列化留证。"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from cg_domain.normalization import normalize_company_name, normalize_name
from cg_domain.orm import Entity, EntityIdentifier


@dataclass(frozen=True)
class PairFeatures:
    left_id: str
    right_id: str
    same_uscc: bool
    same_lei: bool
    same_source_key: bool
    norm_name_equal: bool
    short_name_equal: bool
    name_similarity: float  # 0..1，规范化全名 SequenceMatcher
    kind_match: bool
    identifiers_overlap: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "same_uscc": self.same_uscc,
            "same_lei": self.same_lei,
            "same_source_key": self.same_source_key,
            "norm_name_equal": self.norm_name_equal,
            "short_name_equal": self.short_name_equal,
            "name_similarity": round(self.name_similarity, 6),
            "kind_match": self.kind_match,
            "identifiers_overlap": list(self.identifiers_overlap),
        }


def _identifiers_of(entity_id: str, rows: list[EntityIdentifier]) -> dict[str, set[str]]:
    by_entity: dict[str, dict[str, set[str]]] = {}
    for row in rows:
        by_entity.setdefault(row.entity_id, {}).setdefault(row.namespace, set()).add(row.value)
    return by_entity.get(entity_id, {})


def compute_features(
    left: Entity,
    right: Entity,
    left_ids: list[EntityIdentifier],
    right_ids: list[EntityIdentifier],
) -> PairFeatures:
    left_map = _identifiers_of(left.id, left_ids)
    right_map = _identifiers_of(right.id, right_ids)

    overlap: list[str] = []
    for ns in ("uscc", "lei"):
        shared = left_map.get(ns, set()) & right_map.get(ns, set())
        overlap.extend(f"{ns}:{v}" for v in sorted(shared))

    left_src = left_map.get("src", set())
    right_src = right_map.get("src", set())

    ln = normalize_name(left.primary_name)
    rn = normalize_name(right.primary_name)
    similarity = SequenceMatcher(None, ln, rn).ratio() if ln and rn else 0.0

    return PairFeatures(
        left_id=left.id,
        right_id=right.id,
        same_uscc=bool(left_map.get("uscc", set()) & right_map.get("uscc", set())),
        same_lei=bool(left_map.get("lei", set()) & right_map.get("lei", set())),
        same_source_key=bool(left_src & right_src),
        norm_name_equal=ln == rn and bool(ln),
        short_name_equal=(
            normalize_company_name(left.primary_name) == normalize_company_name(right.primary_name)
            and bool(normalize_company_name(left.primary_name))
        ),
        name_similarity=similarity,
        kind_match=left.kind == right.kind,
        identifiers_overlap=overlap,
    )
