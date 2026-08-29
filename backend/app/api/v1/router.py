"""Version 1 API router composition."""

from fastapi import APIRouter

from app.api.v1 import health
from app.modules.answers import router as answer_router
from app.modules.audit import router as audit_router
from app.modules.documents import router as document_router
from app.modules.identity import admin_router
from app.modules.identity import router as identity_router
from app.modules.ingestion import router as ingestion_router
from app.modules.knowledge_bases import router as knowledge_base_router
from app.modules.operations.router import admin_router as operations_admin_router
from app.modules.retrieval import router as retrieval_router

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(identity_router.router, prefix="/auth", tags=["authentication"])
api_router.include_router(admin_router.router, prefix="/admin", tags=["administration"])
api_router.include_router(audit_router.router, prefix="/admin", tags=["audit"])
api_router.include_router(operations_admin_router, prefix="/admin", tags=["operations"])
api_router.include_router(
    knowledge_base_router.router,
    prefix="/knowledge-bases",
    tags=["knowledge-bases"],
)
api_router.include_router(
    retrieval_router.router,
    prefix="/knowledge-bases",
    tags=["retrieval"],
)
api_router.include_router(
    answer_router.router,
    prefix="/knowledge-bases",
    tags=["answers"],
)
api_router.include_router(
    document_router.knowledge_base_router,
    prefix="/knowledge-bases",
    tags=["documents"],
)
api_router.include_router(
    document_router.document_router,
    prefix="/documents",
    tags=["documents"],
)
api_router.include_router(
    ingestion_router.router,
    prefix="/ingestion-jobs",
    tags=["ingestion-jobs"],
)
