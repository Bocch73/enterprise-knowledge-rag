"""Knowledge base ownership and resource authorization use cases."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.identity.models import User
from app.modules.identity.service import get_user_by_email
from app.modules.knowledge_bases.models import KnowledgeBase, KnowledgeBaseMembership
from app.modules.knowledge_bases.schemas import KnowledgeBaseCreate, MembershipUpsert


async def create_knowledge_base(
    session: AsyncSession,
    owner: User,
    data: KnowledgeBaseCreate,
) -> tuple[KnowledgeBase, str]:
    """Create the container and its owner membership atomically."""
    knowledge_base = KnowledgeBase(
        name=data.name,
        description=data.description,
        owner_id=owner.id,
    )
    knowledge_base.memberships.append(
        KnowledgeBaseMembership(user_id=owner.id, access_level="owner")
    )
    session.add(knowledge_base)
    await session.commit()
    await session.refresh(knowledge_base)
    return knowledge_base, "owner"


async def list_accessible_knowledge_bases(
    session: AsyncSession,
    user: User,
) -> list[tuple[KnowledgeBase, str]]:
    """Enforce resource filtering in the database query itself."""
    result = await session.execute(
        select(KnowledgeBase, KnowledgeBaseMembership.access_level)
        .join(
            KnowledgeBaseMembership,
            KnowledgeBaseMembership.knowledge_base_id == KnowledgeBase.id,
        )
        .where(KnowledgeBaseMembership.user_id == user.id)
        .order_by(KnowledgeBase.created_at, KnowledgeBase.id)
    )
    return [(knowledge_base, access) for knowledge_base, access in result.all()]


async def get_accessible_knowledge_base(
    session: AsyncSession,
    user: User,
    knowledge_base_id: UUID,
) -> tuple[KnowledgeBase, str]:
    """Return 404 for absent and unauthorized resources to limit enumeration."""
    result = await session.execute(
        select(KnowledgeBase, KnowledgeBaseMembership.access_level)
        .join(
            KnowledgeBaseMembership,
            KnowledgeBaseMembership.knowledge_base_id == KnowledgeBase.id,
        )
        .where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBaseMembership.user_id == user.id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise AppError(
            code="knowledge_base_not_found",
            message="Knowledge base was not found",
            status_code=404,
        )
    return row[0], row[1]


async def upsert_membership(
    session: AsyncSession,
    actor: User,
    knowledge_base_id: UUID,
    data: MembershipUpsert,
) -> tuple[KnowledgeBaseMembership, str]:
    """Allow only the resource owner or a global administrator to grant access."""
    knowledge_base = await session.get(KnowledgeBase, knowledge_base_id)
    if knowledge_base is None:
        raise AppError(
            code="knowledge_base_not_found",
            message="Knowledge base was not found",
            status_code=404,
        )

    actor_membership = await session.get(
        KnowledgeBaseMembership,
        (knowledge_base_id, actor.id),
    )
    is_owner = actor_membership is not None and actor_membership.access_level == "owner"
    if not is_owner and not actor.has_role("admin"):
        raise AppError(
            code="permission_denied",
            message="Knowledge base owner permission is required",
            status_code=403,
        )

    target_user = await get_user_by_email(session, str(data.email))
    if target_user is None:
        raise AppError(
            code="user_not_found",
            message="User was not found",
            status_code=404,
        )
    if target_user.id == knowledge_base.owner_id:
        raise AppError(
            code="owner_access_immutable",
            message="The knowledge base owner's access cannot be changed",
            status_code=409,
        )

    membership = await session.get(
        KnowledgeBaseMembership,
        (knowledge_base_id, target_user.id),
    )
    if membership is None:
        membership = KnowledgeBaseMembership(
            knowledge_base_id=knowledge_base_id,
            user_id=target_user.id,
            access_level=data.access_level,
        )
        session.add(membership)
    else:
        membership.access_level = data.access_level
    await session.commit()
    await session.refresh(membership)
    return membership, target_user.email
