"""Track project action context and optional blank services.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite can add nullable columns directly but batch mode requires every
    # recreated foreign-key constraint to be named. The service validates the
    # conversation before writing an outcome, so an index is sufficient here.
    op.add_column("project_plans", sa.Column("environment_name", sa.String(80), nullable=False, server_default="production"))
    op.add_column("project_plans", sa.Column("service_name", sa.String(80), nullable=True))
    op.add_column("project_plans", sa.Column("conversation_id", sa.String(36), nullable=True))
    op.create_index("ix_project_plans_conversation_id", "project_plans", ["conversation_id"])


def downgrade() -> None:
    with op.batch_alter_table("project_plans") as batch:
        batch.drop_index("ix_project_plans_conversation_id")
        batch.drop_column("conversation_id")
        batch.drop_column("service_name")
        batch.drop_column("environment_name")
