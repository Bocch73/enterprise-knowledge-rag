"""Create source chunks and fixed-size pgvector embeddings.

Revision ID: 20260828_0003
Revises: 20260826_0002
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260828_0003"
down_revision: str | Sequence[str] | None = "20260826_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 384
STAGES = "'queued', 'parsing', 'chunking', 'embedding', 'indexing', 'completed', 'failed'"


def upgrade() -> None:
    """Require pgvector and add the durable chunk/vector schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                RAISE EXCEPTION
                    'pgvector must be enabled before migration 20260828_0003';
            END IF;
        END
        $$
        """
    )
    op.drop_constraint("ck_ingestion_job_stage", "ingestion_jobs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_job_stage",
        "ingestion_jobs",
        f"stage IN ({STAGES})",
    )

    op.create_table(
        "document_chunks",
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("embedding_dimensions", sa.SmallInteger(), nullable=False),
        sa.Column("embedding", VECTOR(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("chunk_index >= 0", name=op.f("ck_document_chunk_index")),
        sa.CheckConstraint(
            "character_count > 0",
            name=op.f("ck_document_chunk_character_count"),
        ),
        sa.CheckConstraint(
            "start_offset >= 0",
            name=op.f("ck_document_chunk_start_offset"),
        ),
        sa.CheckConstraint(
            "end_offset > start_offset",
            name=op.f("ck_document_chunk_offsets"),
        ),
        sa.CheckConstraint(
            f"embedding_dimensions = {EMBEDDING_DIMENSIONS}",
            name=op.f("ck_document_chunk_embedding_dimensions"),
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name=op.f("fk_document_chunks_document_version_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint(
            "document_version_id",
            "chunk_index",
            name=op.f("uq_document_chunk_version_index"),
        ),
    )
    op.create_index(
        op.f("ix_document_chunks_document_version_id"),
        "document_chunks",
        ["document_version_id"],
    )

    # Jobs completed before this migration only parsed their documents. Requeue
    # them once so the upgraded worker can produce the missing chunks and vectors.
    op.execute(
        """
        UPDATE ingestion_jobs AS job
        SET status = 'queued',
            stage = 'queued',
            progress = 0,
            retryable = TRUE,
            available_at = CURRENT_TIMESTAMP,
            started_at = NULL,
            finished_at = NULL,
            locked_at = NULL,
            worker_id = NULL,
            error_code = NULL,
            error_message = NULL
        WHERE job.status = 'completed'
          AND EXISTS (
              SELECT 1
              FROM parsed_documents AS parsed
              WHERE parsed.document_version_id = job.document_version_id
          )
        """
    )


def downgrade() -> None:
    """Remove vectors and restore the parsing-only task stages."""
    op.drop_index(op.f("ix_document_chunks_document_version_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
    op.execute(
        """
        UPDATE ingestion_jobs
        SET status = 'queued',
            stage = 'queued',
            progress = 0,
            available_at = CURRENT_TIMESTAMP,
            locked_at = NULL,
            worker_id = NULL
        WHERE stage IN ('chunking', 'embedding', 'indexing')
        """
    )
    op.drop_constraint("ck_ingestion_job_stage", "ingestion_jobs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_job_stage",
        "ingestion_jobs",
        "stage IN ('queued', 'parsing', 'completed', 'failed')",
    )
