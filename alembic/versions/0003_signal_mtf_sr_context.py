"""Add mtf_context and sr_context columns to signals table

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signals",
        sa.Column("mtf_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("sr_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("signals", "sr_context")
    op.drop_column("signals", "mtf_context")
