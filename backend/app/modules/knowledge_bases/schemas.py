"""Public schemas for knowledge base ownership and membership."""

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.modules.knowledge_bases.models import KnowledgeBase, KnowledgeBaseMembership

KnowledgeBaseAccess = Literal["owner", "editor", "viewer"]


class KnowledgeBaseCreate(BaseModel):
    """Validated input for an empty knowledge base container."""

    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("name must contain at least two visible characters")
        return cleaned


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base data plus the caller's effective resource permission."""

    id: UUID
    name: str
    description: str | None
    owner_id: UUID
    access_level: KnowledgeBaseAccess
    created_at: datetime

    @classmethod
    def from_model(
        cls,
        knowledge_base: KnowledgeBase,
        access_level: str,
    ) -> "KnowledgeBaseResponse":
        return cls(
            id=knowledge_base.id,
            name=knowledge_base.name,
            description=knowledge_base.description,
            owner_id=knowledge_base.owner_id,
            access_level=cast(KnowledgeBaseAccess, access_level),
            created_at=knowledge_base.created_at,
        )


class MembershipUpsert(BaseModel):
    """Add a user or change their access without exposing database identifiers."""

    email: EmailStr
    access_level: Literal["editor", "viewer"]


class MembershipResponse(BaseModel):
    """Safe representation of one resource permission assignment."""

    knowledge_base_id: UUID
    user_id: UUID
    email: str
    access_level: KnowledgeBaseAccess

    @classmethod
    def from_model(
        cls,
        membership: KnowledgeBaseMembership,
        email: str,
    ) -> "MembershipResponse":
        return cls(
            knowledge_base_id=membership.knowledge_base_id,
            user_id=membership.user_id,
            email=email,
            access_level=cast(KnowledgeBaseAccess, membership.access_level),
        )
