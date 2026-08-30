"""Boundary-aware chunking, test embeddings, and pgvector persistence tests."""

import asyncio
import math
from itertools import pairwise
from typing import cast
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import Database
from app.modules.indexing.chunking import split_text
from app.modules.indexing.models import DocumentChunk
from app.modules.indexing.providers import (
    EMBEDDING_DIMENSIONS,
    DeterministicTestEmbeddingProvider,
)
from app.modules.ingestion.models import IngestionJob
from app.modules.ingestion.worker import process_next_job
from tests.test_authentication import authorization_header, login_user, register_user
from tests.test_document_ingestion import create_knowledge_base, upload_markdown


def run_one_worker(settings: Settings) -> UUID | None:
    async def run() -> UUID | None:
        database = Database(settings)
        try:
            return await process_next_job(database, settings, worker_id="indexing-test-worker")
        finally:
            await database.dispose()

    return asyncio.run(run())


def test_chunker_preserves_offsets_size_and_overlap() -> None:
    text = (
        "第一段介绍员工年假制度。员工每年可以申请带薪年假。\n\n"
        "第二段介绍报销规则。出差费用需要在三十天内提交。\n\n"
        "Third section explains information security. Passwords must not be shared."
    )

    chunks = split_text(text, chunk_size=60, overlap=12)

    assert len(chunks) >= 3
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.content == text[chunk.start_offset : chunk.end_offset] for chunk in chunks)
    assert all(0 < len(chunk.content) <= 60 for chunk in chunks)
    assert all(len(chunk.content_sha256) == 64 for chunk in chunks)
    assert all(current.start_offset < previous.end_offset for previous, current in pairwise(chunks))


def test_deterministic_test_embedding_is_repeatable_normalized_and_fixed_size() -> None:
    provider = DeterministicTestEmbeddingProvider()

    async def embed() -> tuple[list[float], list[float], list[float]]:
        first_batch = await provider.embed_documents(["员工年假 policy", "费用报销"])
        repeated = await provider.embed_documents(["员工年假 policy"])
        return first_batch[0], first_batch[1], repeated[0]

    first, different, repeated = asyncio.run(embed())

    assert len(first) == EMBEDDING_DIMENSIONS
    assert first == repeated
    assert first != different
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_worker_persists_queryable_vectors_and_stable_chunks(
    client: TestClient,
    settings: Settings,
) -> None:
    settings.chunk_size_characters = 100
    settings.chunk_overlap_characters = 20
    register_user(client)
    token = login_user(client)
    knowledge_base_id = create_knowledge_base(client, token)
    content = (
        "# Employee Handbook\n\n"
        + "Annual leave requests must be submitted to the manager. " * 5
        + "\n\nExpense claims require receipts and approval. " * 5
    ).encode()
    uploaded = upload_markdown(client, token, knowledge_base_id, content=content)
    version = cast(dict[str, object], uploaded["version"])
    job = cast(dict[str, object], uploaded["ingestion_job"])

    run_one_worker(settings)
    chunks_response = client.get(
        f"/api/v1/documents/versions/{version['id']}/chunks?limit=100",
        headers=authorization_header(token),
    )
    assert chunks_response.status_code == 200, chunks_response.text
    chunk_page = chunks_response.json()
    assert chunk_page["total"] >= 4
    assert all("embedding" not in item for item in chunk_page["items"])
    assert all(item["embedding_dimensions"] == EMBEDDING_DIMENSIONS for item in chunk_page["items"])
    first_ids = [item["id"] for item in chunk_page["items"]]

    async def inspect_and_requeue() -> float:
        database = Database(settings)
        try:
            async with database.session_factory() as session:
                chunks = list(
                    (
                        await session.scalars(
                            select(DocumentChunk)
                            .where(DocumentChunk.document_version_id == UUID(str(version["id"])))
                            .order_by(DocumentChunk.chunk_index)
                        )
                    ).all()
                )
                assert len(chunks) == chunk_page["total"]
                assert len(chunks[0].embedding) == EMBEDDING_DIMENSIONS
                distance = await session.scalar(
                    select(DocumentChunk.embedding.l2_distance(chunks[0].embedding)).where(
                        DocumentChunk.id == chunks[0].id
                    )
                )
                stored_job = await session.get(IngestionJob, UUID(str(job["id"])))
                assert stored_job is not None
                stored_job.status = "queued"
                stored_job.stage = "queued"
                stored_job.progress = 0
                await session.commit()
                return float(distance or 0.0)
        finally:
            await database.dispose()

    assert math.isclose(asyncio.run(inspect_and_requeue()), 0.0, abs_tol=1e-7)
    run_one_worker(settings)
    repeated = client.get(
        f"/api/v1/documents/versions/{version['id']}/chunks?limit=100",
        headers=authorization_header(token),
    )
    assert repeated.status_code == 200
    assert [item["id"] for item in repeated.json()["items"]] == first_ids


def test_chunk_content_requires_editor_permission(
    client: TestClient,
    settings: Settings,
) -> None:
    register_user(client, email="owner@example.com")
    owner_token = login_user(client, email="owner@example.com")
    knowledge_base_id = create_knowledge_base(client, owner_token)
    uploaded = upload_markdown(client, owner_token, knowledge_base_id)
    version = cast(dict[str, object], uploaded["version"])
    run_one_worker(settings)

    register_user(client, email="viewer@example.com")
    viewer_token = login_user(client, email="viewer@example.com")
    grant = client.put(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/members",
        headers=authorization_header(owner_token),
        json={"email": "viewer@example.com", "access_level": "viewer"},
    )
    assert grant.status_code == 200

    denied = client.get(
        f"/api/v1/documents/versions/{version['id']}/chunks",
        headers=authorization_header(viewer_token),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "permission_denied"
