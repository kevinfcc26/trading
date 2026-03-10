"""learning schema — knowledge_items and model_versions tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("knowledge_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_document", sa.String(255), nullable=True),
        sa.Column("source_section", sa.String(255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, default=1.0),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_knowledge_items_type", "knowledge_items", ["knowledge_type"])
    op.create_index("ix_knowledge_items_source", "knowledge_items", ["source_document"])

    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_type", sa.String(50), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("artifact_path", sa.String(500), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, default="TRAINING"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_model_versions_type_status", "model_versions", ["model_type", "status"])

    op.create_table(
        "experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("model_type", sa.String(50), nullable=False),
        sa.Column("hyperparams", postgresql.JSONB(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, default="running"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("experiments")
    op.drop_table("model_versions")
    op.drop_table("knowledge_items")
