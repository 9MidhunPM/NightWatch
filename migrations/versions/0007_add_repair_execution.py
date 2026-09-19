"""Add typed repair action and verification records.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("action_records", sa.Column("id", sa.String(36), primary_key=True), sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False), sa.Column("repair_plan_id", sa.String(36), sa.ForeignKey("repair_plans.id"), nullable=False), sa.Column("action_type", sa.String(64), nullable=False), sa.Column("target_resource_id", sa.String(512), nullable=False), sa.Column("parameters", sa.JSON(), nullable=False), sa.Column("policy_decision", sa.String(32), nullable=False), sa.Column("approval_id", sa.String(36), sa.ForeignKey("approvals.id"), nullable=True), sa.Column("status", sa.String(16), nullable=False), sa.Column("rollback_state", sa.JSON(), nullable=False), sa.Column("error", sa.String(512), nullable=True), sa.Column("started_at", sa.DateTime(timezone=True), nullable=True), sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("verification_runs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False), sa.Column("action_record_id", sa.String(36), sa.ForeignKey("action_records.id"), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table("verification_checks", sa.Column("id", sa.String(36), primary_key=True), sa.Column("verification_run_id", sa.String(36), sa.ForeignKey("verification_runs.id"), nullable=False), sa.Column("name", sa.String(128), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("observed", sa.String(512), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_action_records_incident_id", "action_records", ["incident_id"])
    op.create_index("ix_action_records_repair_plan_id", "action_records", ["repair_plan_id"])
    op.create_index("ix_verification_runs_incident_id", "verification_runs", ["incident_id"])
    op.create_index("ix_verification_runs_action_record_id", "verification_runs", ["action_record_id"])
    op.create_index("ix_verification_checks_verification_run_id", "verification_checks", ["verification_run_id"])


def downgrade() -> None:
    op.drop_table("verification_checks")
    op.drop_table("verification_runs")
    op.drop_table("action_records")
