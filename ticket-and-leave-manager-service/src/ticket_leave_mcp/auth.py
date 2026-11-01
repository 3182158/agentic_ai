"""Bearer-token verification; the employee identity comes only from a signed token."""

from __future__ import annotations

from collections.abc import Mapping

import jwt


class AuthError(Exception):
    """Raised when a request carries no valid identity."""


def employee_id_from_headers(headers: Mapping[str, str], secret: str) -> str:
    scheme, _, token = headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("Missing bearer token.")
    try:
        claims = jwt.decode(
            token.strip(), secret, algorithms=["HS256"], options={"require": ["exp", "sub"]}
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired token.") from exc
    employee_id = claims["sub"]
    if not isinstance(employee_id, str) or not employee_id.strip():
        raise AuthError("Token has no employee identity.")
    return employee_id.strip().upper()


def idempotency_key_from_headers(headers: Mapping[str, str]) -> str:
    key = headers.get("idempotency-key", "").strip()
    if not key or len(key) > 200:
        raise AuthError("A valid Idempotency-Key header is required for write actions.")
    return key
