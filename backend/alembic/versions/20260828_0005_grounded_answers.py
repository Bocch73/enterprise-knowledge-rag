"""Persist grounded answers and durable citation snapshots.

Revision ID: 20260828_0005
Revises: 20260828_0004
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260828_0005"
down_revision: str | Sequence[str] | None = "20260828_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable question, answer, usage, and source-audit records."""
    op.create_table(
        "grounded_answers",
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("retrieval_method", sa.String(length=100), nullable=False),
        sa.Column("refused", sa.Boolean(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f("fk_grounded_answers_knowledge_base_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_grounded_answers_user_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grounded_answers")),
    )
    op.create_index(
        op.f("ix_grounded_answers_knowledge_base_id"),
        "grounded_answers",
        ["knowledge_base_id"],
    )
    op.create_index(op.f("ix_grounded_answers_user_id"), "grounded_answers", ["user_id"])

    op.create_table(
        "answer_citations",
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("citation_number", sa.Integer(), nullable=False),
        sa.Column("document_id_snapshot", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_title_snapshot", sa.String(length=200), nullable=False),
        sa.Column("document_version_id_snapshot", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number_snapshot", sa.Integer(), nullable=False),
        sa.Column("original_filename_snapshot", sa.String(length=255), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("quoted_text_snapshot", sa.Text(), nullable=False),
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
        sa.CheckConstraint("chunk_index >= 0", name=op.f("ck_answer_citation_chunk_index")),
        sa.CheckConstraint("citation_number > 0", name=op.f("ck_answer_citation_number_positive")),
        sa.CheckConstraint("end_offset > start_offset", name=op.f("ck_answer_citation_offsets")),
        sa.CheckConstraint("start_offset >= 0", name=op.f("ck_answer_citation_start_offset")),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["grounded_answers.id"],
            name=op.f("fk_answer_citations_answer_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_answer_citations_chunk_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_citations")),
        sa.UniqueConstraint("answer_id", "citation_number", name=op.f("uq_answer_citation_number")),
    )
    op.create_index(op.f("ix_answer_citations_answer_id"), "answer_citations", ["answer_id"])
    op.create_index(op.f("ix_answer_citations_chunk_id"), "answer_citations", ["chunk_id"])


def downgrade() -> None:
    """Remove answer audit storage in dependency order."""
    op.drop_index(op.f("ix_answer_citations_chunk_id"), table_name="answer_citations")
    op.drop_index(op.f("ix_answer_citations_answer_id"), table_name="answer_citations")
    op.drop_table("answer_citations")
    op.drop_index(op.f("ix_grounded_answers_user_id"), table_name="grounded_answers")
    op.drop_index(op.f("ix_grounded_answers_knowledge_base_id"), table_name="grounded_answers")
    op.drop_table("grounded_answers")
