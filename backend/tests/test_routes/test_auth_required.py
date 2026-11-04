# AC-A.1: without a valid Better Auth JWT every route except health is 401, and no route
# takes a user id from the request. Tokens are verified against a real local JWKS.
import re

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.main import app
from tests.utils.auth import AUTH_BASE_URL, bearer_headers, mint_token

PUBLIC_ROUTES = {("GET", "/")}

# The OpenAPI schema is the API's public contract: every route, its parameters and body.
OPENAPI = app.openapi()
OPERATIONS = [
    (method.upper(), path, operation)
    for path, methods in OPENAPI["paths"].items()
    for method, operation in methods.items()
]


def protected_requests() -> list[tuple[str, str]]:
    return [
        (method, re.sub(r"{[^}]+}", "000000000000000000000000", path))
        for method, path, _ in OPERATIONS
        if (method, path) not in PUBLIC_ROUTES
    ]


def request_field_names(operation: dict[str, object]) -> set[str]:
    names = {param["name"] for param in operation.get("parameters", [])}
    body = operation.get("requestBody", {})
    for media in body.get("content", {}).values():
        schema = media["schema"]
        if "$ref" in schema:
            schema = OPENAPI["components"]["schemas"][schema["$ref"].split("/")[-1]]
        names |= set(schema.get("properties", {}))
    return names


@pytest.fixture
def anonymous_client():
    with TestClient(app) as client:
        yield client


def test_routes_are_enumerated():
    assert len(protected_requests()) >= 8


@pytest.mark.parametrize(("method", "path"), protected_requests())
def test_route_without_token_is_401(anonymous_client, method, path):
    response = anonymous_client.request(method, path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_health_route_is_public(anonymous_client):
    assert anonymous_client.get("/").status_code == 200


@pytest.mark.parametrize(
    ("method", "path", "operation"), OPERATIONS, ids=[f"{m} {p}" for m, p, _ in OPERATIONS]
)
def test_no_route_accepts_a_user_id(method, path, operation):
    assert not {name for name in request_field_names(operation) if "user_id" in name.lower()}


def test_valid_token_identifies_the_owner(anonymous_client):
    response = anonymous_client.get("/api/v1/settings", headers=bearer_headers("owner-a"))

    assert response.status_code == 200
    assert response.json()["user_id"] == "owner-a"


def test_user_id_query_param_cannot_switch_user(anonymous_client):
    response = anonymous_client.get(
        "/api/v1/settings?user_id=someone-else", headers=bearer_headers("owner-a")
    )

    assert response.json()["user_id"] == "owner-a"


@pytest.mark.parametrize(
    "token",
    [
        mint_token("owner-a", AUTH_BASE_URL, signing_key=Ed25519PrivateKey.generate()),
        mint_token("owner-a", AUTH_BASE_URL, expires_in=-60),
        mint_token("owner-a", "http://evil.example"),
        "not-a-jwt",
    ],
    ids=["foreign-key", "expired", "wrong-issuer", "garbage"],
)
def test_bad_token_is_401(anonymous_client, token):
    response = anonymous_client.get(
        "/api/v1/settings", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
