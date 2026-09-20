"""Add approval-gated everyday Dokploy action plans.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dokploy_action_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_kind", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(160), nullable=False),
        sa.Column("target_name", sa.String(160), nullable=False),
        sa.Column("project_name", sa.String(120), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("expected_state", sa.Text(), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("policy_reason", sa.String(512), nullable=False),
        sa.Column("detail", sa.String(1024), nullable=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("agent_conversations.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dokploy_action_plans_conversation_id", "dokploy_action_plans", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("dokploy_action_plans")
