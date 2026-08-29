"""Validated grounded-answer requests and citation-rich responses."""

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class GroundedAnswerRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("question must contain at least two visible characters")
        return cleaned


class AnswerCitationResponse(BaseModel):
    citation: str
    chunk_id: UUID
    document_id: UUID
    document_title: str
    document_version_id: UUID
    version_number: int
    original_filename: str
    chunk_index: int
    start_offset: int
    end_offset: int
    quoted_text: str


class GroundedAnswerResponse(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    question: str
    answer: str
    model: str
    retrieval_method: str
    refused: bool
    citations: list[AnswerCitationResponse]
