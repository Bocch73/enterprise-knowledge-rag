"""Resource ownership, membership, and horizontal authorization tests."""

from fastapi.testclient import TestClient

from tests.test_authentication import authorization_header, login_user, register_user


def test_owner_creates_and_lists_knowledge_base(client: TestClient) -> None:
    owner = register_user(client, email="owner@example.com")
    token = login_user(client, email="owner@example.com")

    create_response = client.post(
        "/api/v1/knowledge-bases",
        headers=authorization_header(token),
        json={"name": "Employee Handbook", "description": "Internal policies"},
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["owner_id"] == owner["id"]
    assert created["access_level"] == "owner"

    list_response = client.get(
        "/api/v1/knowledge-bases",
        headers=authorization_header(token),
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]


def test_unrelated_user_cannot_discover_knowledge_base(client: TestClient) -> None:
    register_user(client, email="owner@example.com")
    owner_token = login_user(client, email="owner@example.com")
    created = client.post(
        "/api/v1/knowledge-bases",
        headers=authorization_header(owner_token),
        json={"name": "Private Base"},
    ).json()

    register_user(client, email="outsider@example.com")
    outsider_token = login_user(client, email="outsider@example.com")
    response = client.get(
        f"/api/v1/knowledge-bases/{created['id']}",
        headers=authorization_header(outsider_token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "knowledge_base_not_found"


def test_owner_grants_viewer_access_but_viewer_cannot_manage_members(client: TestClient) -> None:
    register_user(client, email="owner@example.com")
    owner_token = login_user(client, email="owner@example.com")
    knowledge_base = client.post(
        "/api/v1/knowledge-bases",
        headers=authorization_header(owner_token),
        json={"name": "Shared Base"},
    ).json()

    register_user(client, email="viewer@example.com")
    viewer_token = login_user(client, email="viewer@example.com")
    register_user(client, email="third@example.com")

    grant_response = client.put(
        f"/api/v1/knowledge-bases/{knowledge_base['id']}/members",
        headers=authorization_header(owner_token),
        json={"email": "viewer@example.com", "access_level": "viewer"},
    )
    assert grant_response.status_code == 200
    assert grant_response.json()["access_level"] == "viewer"

    read_response = client.get(
        f"/api/v1/knowledge-bases/{knowledge_base['id']}",
        headers=authorization_header(viewer_token),
    )
    assert read_response.status_code == 200
    assert read_response.json()["access_level"] == "viewer"

    forbidden_response = client.put(
        f"/api/v1/knowledge-bases/{knowledge_base['id']}/members",
        headers=authorization_header(viewer_token),
        json={"email": "third@example.com", "access_level": "editor"},
    )
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["error"]["code"] == "permission_denied"


def test_authentication_is_required_for_knowledge_bases(client: TestClient) -> None:
    response = client.get("/api/v1/knowledge-bases")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
