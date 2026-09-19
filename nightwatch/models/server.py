from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, BigInteger, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from nightwatch.storage.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    endpoint: Mapped[str] = mapped_column(String(512))
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connection_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    environment: Mapped[str] = mapped_column(String(16), default="LOCAL")
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    node_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    os_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kernel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    architecture: Mapped[str | None] = mapped_column(String(128), nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cpu_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_total_bytes: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    memory_used_bytes: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    root_disk_total_bytes: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    root_disk_used_bytes: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    load_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
