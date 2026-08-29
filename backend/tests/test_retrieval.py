"""Hybrid ranking, authorization, isolation, and version-selection tests."""

import asyncio
from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import Database
from app.modules.ingestion.worker import process_next_job
from app.modules.retrieval.fusion import (
    RankedCandidate,
    RetrievalCandidate,
    reciprocal_rank_fusion,
)
from tests.test_authentication import authorization_header, login_user, register_user
from tests.test_document_ingestion import create_knowledge_base, upload_markdown


def run_one_worker(settings: Settings) -> UUID | None:
    async def run() -> UUID | None:
        database = Database(settings)
        try:
            return await process_next_job(database, settings, worker_id="retrieval-test-worker")
        finally:
            await database.dispose()

    return asyncio.run(run())


def candidate(title: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title=title,
        document_version_id=uuid4(),
        version_number=1,
        original_filename=f"{title}.md",
        chunk_index=0,
        content=title,
        start_offset=0,
        end_offset=len(title),
    )


def test_reciprocal_rank_fusion_rewards_candidates_found_by_both_routes() -> None:
    vector_only = candidate("vector-only")
    shared = candidate("shared")
    keyword_only = candidate("keyword-only")

    results = reciprocal_rank_fusion(
        [RankedCandidate(vector_only, 0.1), RankedCandidate(shared, 0.2)],
        [RankedCandidate(shared, 0.9), RankedCandidate(keyword_only, 0.8)],
        rank_constant=60,
        limit=3,
    )

    assert results[0].candidate.chunk_id == shared.chunk_id
    assert results[0].vector_rank == 2
    assert results[0].keyword_rank == 1
    assert results[0].fused_score > results[1].fused_score


def test_hybrid_search_returns_transparent_ranked_results(
    client: TestClient,
    settings: Settings,
) -> None:
    register_user(client)
    token = login_user(client)
    knowledge_base_id = create_knowledge_base(client, token)
    security = upload_markdown(
        client,
        token,
        knowledge_base_id,
        content=(
            b"# Security Policy\n\nPolicy code SEC-104 requires employees to rotate "
            b"passwords every ninety days."
        ),
        filename="security.md",
    )
    run_one_worker(settings)
    upload_markdown(
        client,
        token,
        knowledge_base_id,
        content=b"# Travel Policy\n\nExpense claims require receipts and manager approval.",
        filename="travel.md",
    )
    run_one_worker(settings)

    response = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/search",
        headers=authorization_header(token),
        json={"query": "SEC-104 passwords", "top_k": 2},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["retrieval_method"] == "hybrid_reciprocal_rank_fusion"
    assert payload["embedding_model"] == "deterministic-hash-v1"
    assert payload["results"]
    first = payload["results"][0]
    security_document = cast(dict[str, object], security["document"])
    assert first["document_id"] == security_document["id"]
    assert first["keyword_rank"] == 1
    assert first["vector_rank"] is not None
    assert first["fused_score"] > 0
    assert "embedding" not in first

    special_characters = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/search",
        headers=authorization_header(token),
        json={"query": '""" )( dummy <->', "top_k": 2},
    )
    assert special_characters.status_code == 200

    blank_query = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/search",
        headers=authorization_header(token),
        json={"query": "   ", "top_k": 2},
    )
    excessive_limit = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/search",
        headers=authorization_header(token),
        json={"query": "security", "top_k": 21},
    )
    assert blank_query.status_code == 422
    assert excessive_limit.status_code == 422


def test_search_enforces_membership_and_knowledge_base_isolation(
    client: TestClient,
    settings: Settings,
) -> None:
    register_user(client, email="owner@example.com")
    owner_token = login_user(client, email="owner@example.com")
    first_base_id = create_knowledge_base(client, owner_token, name="First Base")
    second_base_id = create_knowledge_base(client, owner_token, name="Second Base")
    first_document = upload_markdown(
        client,
        owner_token,
        first_base_id,
        content=b"First base contains project code ALPHA-ONLY.",
        filename="alpha.md",
    )
    run_one_worker(settings)
    second_document = upload_markdown(
        client,
        owner_token,
        second_base_id,
        content=b"Second base contains confidential code BETA-SECRET.",
        filename="beta.md",
    )
    run_one_worker(settings)

    register_user(client, email="viewer@example.com")
    viewer_token = login_user(client, email="viewer@example.com")
    grant = client.put(
        f"/api/v1/knowledge-bases/{first_base_id}/members",
        headers=authorization_header(owner_token),
        json={"email": "viewer@example.com", "access_level": "viewer"},
    )
    assert grant.status_code == 200

    allowed = client.post(
        f"/api/v1/knowledge-bases/{first_base_id}/search",
        headers=authorization_header(viewer_token),
        json={"query": "BETA-SECRET"},
    )
    denied = client.post(
        f"/api/v1/knowledge-bases/{second_base_id}/search",
        headers=authorization_header(viewer_token),
        json={"query": "BETA-SECRET"},
    )

    assert allowed.status_code == 200
    first_document_data = cast(dict[str, object], first_document["document"])
    second_document_data = cast(dict[str, object], second_document["document"])
    assert all(
        result["document_id"] == first_document_data["id"]
        and result["document_id"] != second_document_data["id"]
        for result in allowed.json()["results"]
    )
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "knowledge_base_not_found"


def test_search_uses_latest_completed_document_version(
    client: TestClient,
    settings: Settings,
) -> None:
    register_user(client)
    token = login_user(client)
    knowledge_base_id = create_knowledge_base(client, token)
    uploaded = upload_markdown(
        client,
        token,
        knowledge_base_id,
        content=b"Legacy leave policy requires manager approval.",
        filename="leave-v1.md",
    )
    document = cast(dict[str, object], uploaded["document"])
    run_one_worker(settings)

    second = client.post(
        f"/api/v1/documents/{document['id']}/versions",
        headers=authorization_header(token),
        files={
            "file": (
                "leave-v2.md",
                b"Current leave policy requires human resources approval.",
                "text/markdown",
            )
        },
    )
    assert second.status_code == 201

    while_pending = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/search",
        headers=authorization_header(token),
        json={"query": "manager approval"},
    )
    assert while_pending.status_code == 200
    assert {item["version_number"] for item in while_pending.json()["results"]} == {1}

    run_one_worker(settings)
    after_completion = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/search",
        headers=authorization_header(token),
        json={"query": "human resources approval"},
    )
    assert after_completion.status_code == 200
    assert {item["version_number"] for item in after_completion.json()["results"]} == {2}
