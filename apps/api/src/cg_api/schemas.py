"""HTTP 响应模型（出站 schema）。入站校验直接用 Pydantic 内联模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    primary_name: str
    merged_into_id: str | None = None


class EntityHit(EntityOut):
    score: float | None = None


class SearchOut(BaseModel):
    total: int
    hits: list[EntityHit]


class AliasOut(BaseModel):
    name: str
    alias_type: str
    lang: str


class IdentifierOut(BaseModel):
    namespace: str
    value: str


class SecurityOut(BaseModel):
    code: str
    exchange: str
    security_type: str


class StatementOut(BaseModel):
    id: str
    subject_id: str
    predicate: str
    object_id: str
    share_ratio_percent: float | None
    voting_ratio_percent: float | None
    control_type: str | None
    valid_from: str
    valid_to: str | None
    status: str
    claim_basis: str
    confidence: float
    source_url: str
    note: str
    superseded_by_id: str | None = None


class EntityDetailOut(BaseModel):
    id: str
    kind: str
    primary_name: str
    merged_into_id: str | None
    aliases: list[AliasOut]
    identifiers: list[IdentifierOut]
    securities: list[SecurityOut]
    incoming: list[StatementOut]
    outgoing: list[StatementOut]


class HistoryOut(BaseModel):
    statements: list[StatementOut]


class EvidenceOut(BaseModel):
    statement_id: str
    fragments: list[dict[str, Any]]


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class IngestRunIn(BaseModel):
    connector: str
    params: dict[str, str] = {}


class IngestRunOut(BaseModel):
    status: str
    stats: dict[str, Any] | None = None
    message: str = ""


class ReviewResolveIn(BaseModel):
    note: str


class UserCreateIn(BaseModel):
    username: str
    password: str
    role: str
