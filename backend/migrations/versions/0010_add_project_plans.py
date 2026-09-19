"""Add approval-gated blank Dokploy project plans.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("project_name", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("policy_reason", sa.String(512), nullable=False),
        sa.Column("detail", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("project_plans")
