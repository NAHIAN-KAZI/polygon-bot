import re
from dataclasses import dataclass

import httpx

from app.config import settings

_BEARER_RE = re.compile(r"^Bearer (\S+)$")


@dataclass(frozen=True)
class CustomerIdentity:
    customer_id: str


def extract_jwt(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    match = _BEARER_RE.match(authorization_header)
    if not match:
        return None
    return match.group(1)


async def verify_jwt(token: str) -> CustomerIdentity | None:
    """Real verification via remote token introspection (ADR-0008 amendment,
    revised 2026-09-03): the bank does not hand out its JWT signing secret, so
    instead of verifying the signature locally, this asks the bank's own auth
    service to verify the token and tell us who it belongs to. Never raises —
    any failure (network error, non-200 response, missing/malformed claims)
    returns None (NFR-SEC-01 fail-closed). Never logs the raw token."""
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.PLATFORM_API_BASE_URL}/auth/v1/auth/session",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError:
        return None

    if resp.status_code != 200:
        return None

    try:
        data = resp.json()
    except ValueError:
        return None

    phone = data.get("phone")
    if not phone or not isinstance(phone, str):
        return None

    return CustomerIdentity(customer_id=phone)


class AuthRequiredError(Exception):
    """Raised when a banking-service-eligible request has no valid customer identity."""


async def require_customer_identity(authorization_header: str | None) -> CustomerIdentity:
    token = extract_jwt(authorization_header)
    if token is None:
        raise AuthRequiredError

    identity = await verify_jwt(token)
    if identity is None:
        raise AuthRequiredError

    return identity
