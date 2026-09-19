"""Add local-host metrics to the managed server registry."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, type_ in (
        ("os_name", sa.String(length=255)),
        ("kernel", sa.String(length=255)),
        ("architecture", sa.String(length=128)),
        ("uptime_seconds", sa.Integer()),
        ("cpu_count", sa.Integer()),
        ("cpu_percent", sa.Float()),
        ("memory_total_bytes", sa.BigInteger()),
        ("memory_used_bytes", sa.BigInteger()),
        ("root_disk_total_bytes", sa.BigInteger()),
        ("root_disk_used_bytes", sa.BigInteger()),
        ("load_1m", sa.Float()),
    ):
        op.add_column("servers", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name in (
        "load_1m", "root_disk_used_bytes", "root_disk_total_bytes", "memory_used_bytes",
        "memory_total_bytes", "cpu_percent", "cpu_count", "uptime_seconds", "architecture",
        "kernel", "os_name",
    ):
        op.drop_column("servers", name)
