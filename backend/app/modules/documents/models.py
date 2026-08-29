"""Document identity and immutable source-version models."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.indexing.models import DocumentChunk


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A logical document whose source may have multiple immutable versions."""

    __tablename__ = "documents"

    knowledge_base_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DocumentVersion.version_number",
    )


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An immutable source file and its integrity metadata."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
        UniqueConstraint("document_id", "sha256", name="uq_document_version_sha256"),
        CheckConstraint("version_number > 0", name="ck_document_version_number_positive"),
        CheckConstraint("size_bytes > 0", name="ck_document_version_size_positive"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    uploaded_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document: Mapped[Document] = relationship(back_populates="versions")
    parsed_content: Mapped[ParsedDocument | None] = relationship(
        back_populates="document_version",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document_version",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DocumentChunk.chunk_index",
    )


class ParsedDocument(TimestampMixin, Base):
    """Extracted text for one immutable source version before chunking."""

    __tablename__ = "parsed_documents"
    __table_args__ = (
        CheckConstraint("character_count >= 0", name="ck_parsed_document_character_count"),
        CheckConstraint(
            "page_count IS NULL OR page_count > 0", name="ck_parsed_document_page_count"
        ),
    )

    document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parser_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    document_version: Mapped[DocumentVersion] = relationship(back_populates="parsed_content")
