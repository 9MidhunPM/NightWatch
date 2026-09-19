"""Reset persisted app-server threads so every resumed conversation starts on Luna.

Revision ID: 0014_reset_legacy_codex_threads
Revises: 0013
"""

from alembic import op


revision = "0014_reset_legacy_codex_threads"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE agent_conversations SET codex_thread_id = NULL WHERE codex_thread_id IS NOT NULL")


def downgrade() -> None:
    pass
