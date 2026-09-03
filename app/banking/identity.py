import re
from dataclasses import dataclass

import jwt

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


def verify_jwt(token: str) -> CustomerIdentity | None:
    """Real HS256 verification (ADR-0008 amendment 2026-09-03).

    A live login against the bank's dev environment confirmed the algorithm
    and claims shape: HS256 (symmetric shared secret), `sub` is the
    customer's phone number and is the session key per ADR-0005, `iss` is
    the literal string "internet-banking", no `aud` claim, ~15-minute
    lifetime. Only the actual shared secret value remains pending from the
    bank — until `JWT_HS256_SECRET` is configured, this stays fail-closed
    per NFR-SEC-01: an unconfigured or unverifiable token is never treated
    as valid. Never raises, and never logs the raw token, secret, or
    decoded claims.
    """
    if not settings.JWT_HS256_SECRET:
        return None  # NFR-SEC-01: no signing configuration = fail closed

    try:
        decode_kwargs = {"algorithms": [settings.JWT_ALGORITHM], "leeway": settings.JWT_LEEWAY_SECONDS}
        if settings.JWT_ISSUER:
            decode_kwargs["issuer"] = settings.JWT_ISSUER
        claims = jwt.decode(token, settings.JWT_HS256_SECRET, **decode_kwargs,
                             options={"verify_aud": False})  # no aud claim exists on this token

        sub = claims.get("sub")
        if not sub or not isinstance(sub, str):
            return None  # ADR-0005: session key IS sub; no sub, no identity

        return CustomerIdentity(customer_id=sub)

    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidIssuerError:
        return None
    except jwt.InvalidSignatureError:
        return None
    except jwt.DecodeError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None


class AuthRequiredError(Exception):
    """Raised when a banking-service-eligible request has no valid customer identity."""


def require_customer_identity(authorization_header: str | None) -> CustomerIdentity:
    token = extract_jwt(authorization_header)
    if token is None:
        raise AuthRequiredError

    identity = verify_jwt(token)
    if identity is None:
        raise AuthRequiredError

    return identity
