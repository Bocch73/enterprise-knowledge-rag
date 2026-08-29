"""Durable ingestion job state used across API and worker processes."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IngestionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The durable, retryable processing state for one document version."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_ingestion_job_status",
        ),
        CheckConstraint(
            "stage IN ("
            "'queued', 'parsing', 'chunking', 'embedding', 'indexing', 'completed', 'failed'"
            ")",
            name="ck_ingestion_job_stage",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_ingestion_job_progress"),
        CheckConstraint("attempt_count >= 0", name="ck_ingestion_job_attempt_count"),
        CheckConstraint("max_attempts > 0", name="ck_ingestion_job_max_attempts"),
        CheckConstraint("manual_retry_count BETWEEN 0 AND 1", name="ck_ingestion_job_manual_retry"),
        Index("ix_ingestion_jobs_dispatch", "status", "available_at", "created_at"),
    )

    document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    manual_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
