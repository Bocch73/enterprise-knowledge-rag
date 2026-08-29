"""Knowledge base and resource-level membership models."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KnowledgeBase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant-like container that owns documents and access rules."""

    __tablename__ = "knowledge_bases"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    memberships: Mapped[list[KnowledgeBaseMembership]] = relationship(
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class KnowledgeBaseMembership(TimestampMixin, Base):
    """A user's resource-level permission inside one knowledge base."""

    __tablename__ = "knowledge_base_memberships"
    __table_args__ = (
        CheckConstraint(
            "access_level IN ('owner', 'editor', 'viewer')",
            name="ck_kb_membership_access_level",
        ),
    )

    knowledge_base_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    access_level: Mapped[str] = mapped_column(String(20), nullable=False)
    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="memberships")
