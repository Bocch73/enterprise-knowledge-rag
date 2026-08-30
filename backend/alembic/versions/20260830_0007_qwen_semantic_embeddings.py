"""Replace development hash vectors with Qwen semantic embeddings.

Revision ID: 20260830_0007
Revises: 20260828_0006
Create Date: 2026-08-30
"""

from collections.abc import Sequence

from pgvector.sqlalchemy import VECTOR

from alembic import op

revision: str = "20260830_0007"
down_revision: str | Sequence[str] | None = "20260828_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_DIMENSIONS = 384
NEW_DIMENSIONS = 1024


def _reset_completed_jobs() -> None:
    """Queue source documents for safe regeneration with the active provider."""
    op.execute(
        """
        UPDATE ingestion_jobs
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
        WHERE status = 'completed'
        """
    )


def upgrade() -> None:
    """Discard incompatible vectors, expand the column, and add cosine HNSW."""
    op.execute("DELETE FROM document_chunks")
    op.drop_constraint(
        "ck_document_chunk_embedding_dimensions",
        "document_chunks",
        type_="check",
    )
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=VECTOR(OLD_DIMENSIONS),
        type_=VECTOR(NEW_DIMENSIONS),
        existing_nullable=False,
        postgresql_using=f"embedding::vector({NEW_DIMENSIONS})",
    )
    op.create_check_constraint(
        "ck_document_chunk_embedding_dimensions",
        "document_chunks",
        f"embedding_dimensions = {NEW_DIMENSIONS}",
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
    )
    _reset_completed_jobs()


def downgrade() -> None:
    """Return to the former vector width while preserving source documents."""
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.execute("DELETE FROM document_chunks")
    op.drop_constraint(
        "ck_document_chunk_embedding_dimensions",
        "document_chunks",
        type_="check",
    )
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=VECTOR(NEW_DIMENSIONS),
        type_=VECTOR(OLD_DIMENSIONS),
        existing_nullable=False,
        postgresql_using=f"embedding::vector({OLD_DIMENSIONS})",
    )
    op.create_check_constraint(
        "ck_document_chunk_embedding_dimensions",
        "document_chunks",
        f"embedding_dimensions = {OLD_DIMENSIONS}",
    )
    _reset_completed_jobs()
