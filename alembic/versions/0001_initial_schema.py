"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("ta_context", postgresql.JSONB(), nullable=True),
        sa.Column("ml_context", postgresql.JSONB(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("component_signals", postgresql.JSONB(), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_signals_instrument", "signals", ["instrument"])

    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("commission", sa.Float(), default=0.0, nullable=False),
        sa.Column("swap", sa.Float(), default=0.0, nullable=False),
        sa.Column(
            "signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.id"),
            nullable=True,
        ),
        sa.Column("broker_position_id", sa.String(100), default="", nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_trades_instrument", "trades", ["instrument"])
    op.create_index("ix_trades_signal_id", "trades", ["signal_id"])

    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("broker_position_id", sa.String(100), nullable=False, unique=True),
        sa.Column("instrument", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column(
            "signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.id"),
            nullable=True,
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_open", sa.Boolean(), default=True, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_positions_instrument", "positions", ["instrument"])
    op.create_index("ix_positions_is_open", "positions", ["is_open"])


def downgrade() -> None:
    op.drop_table("positions")
    op.drop_table("trades")
    op.drop_table("signals")
