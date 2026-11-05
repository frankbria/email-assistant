# backend/app/auth.py
"""Owner authentication: verify the Better Auth JWT the frontend sends as a bearer token."""

import asyncio
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    # Caches the keys and refetches when a token names an unknown key id (rotation).
    return jwt.PyJWKClient(jwks_url, cache_keys=True)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_owner_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    """The signed-in owner's id (the JWT `sub`). Never taken from the request otherwise."""
    if credentials is None:
        raise unauthorized("Sign in required")
    settings = get_settings()
    token = credentials.credentials
    try:
        # PyJWKClient fetches over blocking HTTP on a cache miss.
        signing_key = await asyncio.to_thread(jwks_client(settings.better_auth_jwks_url).get_signing_key_from_jwt, token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA"],
            issuer=settings.better_auth_url,
            audience=settings.better_auth_url,
            options={"require": ["sub", "exp", "iss", "aud"]},
        )
    except jwt.PyJWKClientConnectionError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Can't verify sign-in right now",
        ) from error
    except jwt.PyJWTError as error:
        raise unauthorized("Invalid or expired sign-in token") from error
    return str(claims["sub"])


OwnerId = Annotated[str, Depends(current_owner_id)]
