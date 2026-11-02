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
PUBLIC_JWK = {**json.loads(OKPAlgorithm.to_jwk(SIGNING_KEY.public_key())), "kid": KEY_ID}


class JwksHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({"keys": [PUBLIC_JWK]}).encode()
        self.send_response(200 if self.path == "/api/auth/jwks" else 404)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # keep test output quiet
        pass


def start_auth_server() -> str:
    """Serve the test JWKS at <base>/api/auth/jwks; returns <base>."""
    server = HTTPServer(("127.0.0.1", 0), JwksHandler)
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
