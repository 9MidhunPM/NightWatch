"""Persist redacted world snapshots and domain monitoring state."""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("world_state", sa.Column("key", sa.String(80), primary_key=True),
                    sa.Column("payload", sa.Text(), nullable=False))


def downgrade() -> None:
    op.drop_table("world_state")
