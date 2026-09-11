"""v0.3 区域/行业维度与结构化金额

Revision ID: a7c31e5b8d20
Revises: 4f9bff304672
Create Date: 2026-09-12

entities.region_code/industry 为标准化层维度列（可空，可回填）；
statements.amount_scaled 为万元×100 缩放整数（AMOUNT_SCALE），与 amount 原始字符串列并存，
聚合口径只使用 amount_scaled。三列均可空，新旧数据无需回填即可共存。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c31e5b8d20"
down_revision: str | None = "4f9bff304672"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("entities", sa.Column("region_code", sa.String(length=6), nullable=True))
    op.add_column("entities", sa.Column("industry", sa.String(length=32), nullable=True))
    op.create_index("ix_entities_region_code", "entities", ["region_code"])
    op.create_index("ix_entities_industry", "entities", ["industry"])
    op.add_column("relationship_statements", sa.Column("amount_scaled", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("relationship_statements", "amount_scaled")
    op.drop_index("ix_entities_industry", table_name="entities")
    op.drop_index("ix_entities_region_code", table_name="entities")
    op.drop_column("entities", "industry")
    op.drop_column("entities", "region_code")
