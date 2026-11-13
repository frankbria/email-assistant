# Issue #120: with BETTER_AUTH_JWKS set, the API trusts only those pinned public keys and never
# the JWKS it could fetch over the network, so a process spoofing the frontend can't mint tokens.
import json
from collections.abc import Iterator

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import app
from tests.utils.auth import AUTH_BASE_URL, KEY_ID, PUBLIC_JWK, mint_token, public_jwk, start_auth_server

ATTACKER_KEY = Ed25519PrivateKey.generate()
SPOOFED_FRONTEND = start_auth_server([public_jwk(ATTACKER_KEY, KEY_ID)])


@pytest.fixture
def pinned_client(monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("BETTER_AUTH_JWKS", json.dumps({"keys": [PUBLIC_JWK]}))
    monkeypatch.setenv("BETTER_AUTH_JWKS_URL", f"{SPOOFED_FRONTEND}/api/auth/jwks")
    get_settings.cache_clear()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def settings_status(client: TestClient, token: str) -> int:
    return client.get("/api/v1/settings", headers={"Authorization": f"Bearer {token}"}).status_code


def test_a_token_signed_with_the_pinned_key_is_accepted(pinned_client):
    assert settings_status(pinned_client, mint_token("owner-a", AUTH_BASE_URL)) == 200


def test_a_key_served_by_a_spoofed_frontend_is_not_trusted(pinned_client):
    forged = mint_token("owner-a", AUTH_BASE_URL, signing_key=ATTACKER_KEY)

    assert settings_status(pinned_client, forged) == 401


def test_a_token_naming_a_key_that_is_not_pinned_is_401(pinned_client):
    assert settings_status(pinned_client, mint_token("owner-a", AUTH_BASE_URL, key_id="unpinned-key")) == 401


@pytest.mark.parametrize("pinned", ["not json", '{"keys": []}', '{"keys": [{"kty": "nonsense"}]}'])
def test_a_malformed_pinned_key_set_stops_startup(monkeypatch, pinned):
    monkeypatch.setenv("BETTER_AUTH_JWKS", pinned)

    with pytest.raises(ValidationError, match="BETTER_AUTH_JWKS"):
        Settings()


def test_an_empty_pinned_key_set_means_unpinned(monkeypatch):
    monkeypatch.setenv("BETTER_AUTH_JWKS", "")

    assert Settings().better_auth_jwks is None
