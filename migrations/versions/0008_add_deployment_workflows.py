"""Add approval-gated Dokploy deployment workflows.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployment_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("owner", sa.String(120), nullable=False),
        sa.Column("repository", sa.String(160), nullable=False),
        sa.Column("branch", sa.String(200), nullable=False),
        sa.Column("project_name", sa.String(80), nullable=False),
        sa.Column("environment_name", sa.String(80), nullable=False),
        sa.Column("service_name", sa.String(80), nullable=False),
        sa.Column("build_type", sa.String(32), nullable=False),
        sa.Column("build_path", sa.String(300), nullable=False),
        sa.Column("dockerfile", sa.String(300), nullable=True),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(253), nullable=True),
        sa.Column("secret_names", sa.JSON(), nullable=False),
        sa.Column("manifest_notes", sa.String(3000), nullable=False),
        sa.Column("plan_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("policy_decision", sa.String(32), nullable=False),
        sa.Column("policy_reason", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "deployment_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("deployment_plan_id", sa.String(36), sa.ForeignKey("deployment_plans.id"), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "deployment_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("deployment_plan_id", sa.String(36), sa.ForeignKey("deployment_plans.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("project_id", sa.String(128), nullable=True),
        sa.Column("environment_id", sa.String(128), nullable=True),
        sa.Column("application_id", sa.String(128), nullable=True),
        sa.Column("detail", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_deployment_approvals_deployment_plan_id", "deployment_approvals", ["deployment_plan_id"])
    op.create_index("ix_deployment_executions_deployment_plan_id", "deployment_executions", ["deployment_plan_id"])


def downgrade() -> None:
    op.drop_table("deployment_executions")
    op.drop_table("deployment_approvals")
    op.drop_table("deployment_plans")
