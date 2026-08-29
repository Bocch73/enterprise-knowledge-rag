"""Authenticated knowledge base and membership HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, Request, status

from app.modules.identity.dependencies import CurrentUserDependency, SessionDependency
from app.modules.knowledge_bases.schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    MembershipResponse,
    MembershipUpsert,
)
from app.modules.knowledge_bases.service import (
    create_knowledge_base,
    get_accessible_knowledge_base,
    list_accessible_knowledge_bases,
    upsert_membership,
)

router = APIRouter()


@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create(
    data: KnowledgeBaseCreate,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
) -> KnowledgeBaseResponse:
    knowledge_base, access = await create_knowledge_base(session, current_user, data)
    request.state.audit_resource_id = knowledge_base.id
    return KnowledgeBaseResponse.from_model(knowledge_base, access)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> list[KnowledgeBaseResponse]:
    rows = await list_accessible_knowledge_bases(session, current_user)
    return [
        KnowledgeBaseResponse.from_model(knowledge_base, access) for knowledge_base, access in rows
    ]


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
async def get(
    knowledge_base_id: UUID,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> KnowledgeBaseResponse:
    knowledge_base, access = await get_accessible_knowledge_base(
        session,
        current_user,
        knowledge_base_id,
    )
    return KnowledgeBaseResponse.from_model(knowledge_base, access)


@router.put("/{knowledge_base_id}/members", response_model=MembershipResponse)
async def add_or_update_member(
    knowledge_base_id: UUID,
    data: MembershipUpsert,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
) -> MembershipResponse:
    membership, email = await upsert_membership(
        session,
        current_user,
        knowledge_base_id,
        data,
    )
    request.state.audit_resource_id = knowledge_base_id
    return MembershipResponse.from_model(membership, email)
