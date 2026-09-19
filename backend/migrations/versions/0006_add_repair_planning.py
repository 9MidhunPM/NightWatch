"""Add repair plans, typed changes, and approval records.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repair_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("target_resource_id", sa.String(length=512), nullable=False),
        sa.Column("reason", sa.String(length=1024), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("blast_radius_resource_ids", sa.JSON(), nullable=False),
        sa.Column("expected_downtime", sa.String(length=255), nullable=True),
        sa.Column("verification_plan", sa.JSON(), nullable=False),
        sa.Column("rollback_plan", sa.JSON(), nullable=False),
        sa.Column("policy_decision", sa.String(length=32), nullable=False),
        sa.Column("policy_reason", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("incident_id", "version"),
    )
    op.create_table(
        "repair_changes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "repair_plan_id",
            sa.String(length=36),
            sa.ForeignKey("repair_plans.id"),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target_resource_id", sa.String(length=512), nullable=False),
        sa.Column("field", sa.String(length=255), nullable=False),
        sa.Column("from_value", sa.String(length=512), nullable=True),
        sa.Column("to_value", sa.String(length=512), nullable=True),
        sa.Column("reversible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "repair_plan_id",
            sa.String(length=36),
            sa.ForeignKey("repair_plans.id"),
            nullable=False,
        ),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_repair_plans_incident_id", "repair_plans", ["incident_id"])
    op.create_index("ix_repair_changes_repair_plan_id", "repair_changes", ["repair_plan_id"])
    op.create_index("ix_approvals_repair_plan_id", "approvals", ["repair_plan_id"])


def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_table("repair_changes")
    op.drop_table("repair_plans")
