"""Add managed server registry."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "servers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("connection_status", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("node_version", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_servers_name", "servers", ["name"])


def downgrade() -> None:
    op.drop_index("ix_servers_name", table_name="servers")
    op.drop_table("servers")
