"""Initial backend migration marker."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    pass
