"""Persist deployment plans in the conversation that requested them.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Direct additions are SQLite-safe; avoid batch recreation because older
    # SQLite databases may contain unnamed constraints.
    op.add_column("deployment_plans", sa.Column("conversation_id", sa.String(36), nullable=True))
    op.create_index("ix_deployment_plans_conversation_id", "deployment_plans", ["conversation_id"])


def downgrade() -> None:
    with op.batch_alter_table("deployment_plans") as batch:
        batch.drop_index("ix_deployment_plans_conversation_id")
        batch.drop_column("conversation_id")
