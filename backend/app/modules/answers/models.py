"""Immutable generated answers and citation snapshots."""

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GroundedAnswer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One user question and its validated, retrieval-grounded answer."""

    __tablename__ = "grounded_answers"

    knowledge_base_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    retrieval_method: Mapped[str] = mapped_column(String(100), nullable=False)
    refused: Mapped[bool] = mapped_column(Boolean, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AnswerCitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Source metadata copied at answer time so audit history remains meaningful."""

    __tablename__ = "answer_citations"
    __table_args__ = (
        UniqueConstraint("answer_id", "citation_number", name="uq_answer_citation_number"),
        CheckConstraint("citation_number > 0", name="ck_answer_citation_number_positive"),
        CheckConstraint("chunk_index >= 0", name="ck_answer_citation_chunk_index"),
        CheckConstraint("start_offset >= 0", name="ck_answer_citation_start_offset"),
        CheckConstraint("end_offset > start_offset", name="ck_answer_citation_offsets"),
    )

    answer_id: Mapped[UUID] = mapped_column(
        ForeignKey("grounded_answers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    citation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id_snapshot: Mapped[UUID] = mapped_column(nullable=False)
    document_title_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    document_version_id_snapshot: Mapped[UUID] = mapped_column(nullable=False)
    version_number_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    quoted_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
