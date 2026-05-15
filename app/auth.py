from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import time

from fastapi import HTTPException


AUTH_JWT_ISSUER_ENV = "AUTH_JWT_ISSUER"
AUTH_JWT_AUDIENCE_ENV = "AUTH_JWT_AUDIENCE"
AUTH_JWT_SECRET_ENV = "AUTH_JWT_SECRET"

SCOPE_QUOTES_ADMIN = "quotes:admin"
SCOPE_QUOTES_APPROVE = "quotes:approve"


@dataclass(frozen=True)
class BearerAuthConfig:
    issuer: str
    audience: str
    secret: str


@dataclass(frozen=True)
class AuthenticatedCaller:
    subject: str
    issuer: str
    audience: str | list[str]
    scopes: list[str]
    expires_at: int


def load_bearer_auth_config(environ: dict[str, str] | None = None) -> BearerAuthConfig:
    env = os.environ if environ is None else environ
    return BearerAuthConfig(
        issuer=env.get(AUTH_JWT_ISSUER_ENV, "").strip() or "platform-auth",
        audience=env.get(AUTH_JWT_AUDIENCE_ENV, "").strip() or "quotes-service",
        secret=env.get(AUTH_JWT_SECRET_ENV, "").strip() or "quotes-dev-secret",
    )


def require_bearer_scope(authorization: str | None, required_scope: str) -> AuthenticatedCaller:
    caller = authenticate_bearer_token(authorization, load_bearer_auth_config())
    if required_scope not in caller.scopes:
        raise HTTPException(status_code=403, detail=f"missing required scope {required_scope}")
    return caller


def authenticate_bearer_token(authorization: str | None, config: BearerAuthConfig) -> AuthenticatedCaller:
    token = _parse_bearer_header(authorization)
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="invalid bearer token")

    encoded_header, encoded_payload, encoded_signature = parts
    header = _decode_base64url_json(encoded_header, "invalid bearer token header")
    payload = _decode_base64url_json(encoded_payload, "invalid bearer token payload")

    if header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="unsupported bearer token algorithm")

    expected_signature = hmac.new(
        config.secret.encode(),
        f"{encoded_header}.{encoded_payload}".encode(),
        hashlib.sha256,
    ).digest()
    actual_signature = _decode_base64url(encoded_signature, "invalid bearer token signature")
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise HTTPException(status_code=401, detail="invalid bearer token signature")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(status_code=401, detail="bearer token subject is required")

    issuer = payload.get("iss")
    if issuer != config.issuer:
        raise HTTPException(status_code=401, detail="bearer token issuer is invalid")

    audience = payload.get("aud")
    if not _audience_matches(audience, config.audience):
        raise HTTPException(status_code=401, detail="bearer token audience is invalid")

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        raise HTTPException(status_code=401, detail="bearer token expiry is invalid")
    if expires_at <= int(time.time()):
        raise HTTPException(status_code=401, detail="bearer token is expired")

    return AuthenticatedCaller(
        subject=subject.strip(),
        issuer=issuer,
        audience=audience,
        scopes=_parse_scopes(payload.get("scope")),
        expires_at=expires_at,
    )


def _parse_bearer_header(authorization: str | None) -> str:
    if authorization is None or not authorization.strip():
        raise HTTPException(status_code=401, detail="missing bearer token")

    prefix = "bearer "
    if not authorization.lower().startswith(prefix):
        raise HTTPException(status_code=401, detail="invalid authorization header")

    token = authorization[len(prefix) :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="invalid authorization header")
    return token


def _parse_scopes(raw: object) -> list[str]:
    if not isinstance(raw, str):
        return []
    return [scope for scope in raw.split() if scope]


def _audience_matches(audience: object, expected_audience: str) -> bool:
    if isinstance(audience, str):
        return audience == expected_audience
    if isinstance(audience, list):
        return expected_audience in audience
    return False


def _decode_base64url_json(value: str, message: str) -> dict[str, object]:
    try:
        decoded = _decode_base64url(value, message).decode()
        payload = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail=message) from None

    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail=message)
    return payload


def _decode_base64url(value: str, message: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(f"{value}{padding}")
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=401, detail=message) from None
