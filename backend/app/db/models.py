"""Import every model once so Alembic sees complete metadata."""

from app.modules.answers.models import AnswerCitation, GroundedAnswer
from app.modules.audit.models import AuditEvent
from app.modules.documents.models import Document, DocumentVersion, ParsedDocument
from app.modules.identity.models import Role, User, user_roles
from app.modules.indexing.models import DocumentChunk
from app.modules.ingestion.models import IngestionJob
from app.modules.knowledge_bases.models import KnowledgeBase, KnowledgeBaseMembership

__all__ = [
    "AnswerCitation",
    "AuditEvent",
    "Document",
    "DocumentChunk",
    "DocumentVersion",
    "GroundedAnswer",
    "IngestionJob",
    "KnowledgeBase",
    "KnowledgeBaseMembership",
    "ParsedDocument",
    "Role",
    "User",
    "user_roles",
]
