"""Administrator-facing operational response schemas."""

from pydantic import BaseModel

from app.modules.documents.schemas import IngestionJobResponse


class IngestionJobPage(BaseModel):
    items: list[IngestionJobResponse]
    offset: int
    limit: int
    total: int
