# backend/tests/utils/auth.py
"""Real Ed25519 keys and a real local JWKS endpoint, standing in for Better Auth's."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm

SIGNING_KEY = Ed25519PrivateKey.generate()
KEY_ID = "test-key-1"


def public_jwk(signing_key: Ed25519PrivateKey, key_id: str) -> dict[str, str]:
    jwk: dict[str, str] = json.loads(OKPAlgorithm.to_jwk(signing_key.public_key()))
    return {**jwk, "kid": key_id}


PUBLIC_JWK = public_jwk(SIGNING_KEY, KEY_ID)


class JwksServer(HTTPServer):
    def __init__(self, keys: list[dict[str, str]]) -> None:
        super().__init__(("127.0.0.1", 0), JwksHandler)
        self.keys = keys


class JwksHandler(BaseHTTPRequestHandler):
    server: JwksServer

    def do_GET(self) -> None:
        body = json.dumps({"keys": self.server.keys}).encode()
        self.send_response(200 if self.path == "/api/auth/jwks" else 404)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # keep test output quiet
        pass


def start_auth_server(keys: list[dict[str, str]] | None = None) -> str:
    """Serve these public keys (default: the test key) as the JWKS at <base>/api/auth/jwks; returns <base>."""
    server = JwksServer([PUBLIC_JWK] if keys is None else keys)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}"


def mint_token(
    subject: str,
    issuer: str,
    *,
    signing_key: Ed25519PrivateKey = SIGNING_KEY,
    key_id: str = KEY_ID,
    expires_in: int = 300,
) -> str:
    now = int(time.time())
    claims = {"sub": subject, "iss": issuer, "aud": issuer, "iat": now, "exp": now + expires_in}
    return jwt.encode(claims, signing_key, algorithm="EdDSA", headers={"kid": key_id})


# One server per test session: import these from here, never from conftest (pytest loads
# conftest under its own module name, so importing it again re-runs its top level).
AUTH_BASE_URL = start_auth_server()
OWNER_ID = "test-owner"


def bearer_headers(subject: str = OWNER_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_token(subject, AUTH_BASE_URL)}"}
