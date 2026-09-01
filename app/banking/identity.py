import re
from dataclasses import dataclass

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
    """Fail-closed stub (ADR-0008): the real issuer/algorithm/key for
    customer JWTs are not yet available (BRD Open Item 1), so every token
    is currently treated as unverifiable. The fixed `verify_jwt(token) ->
    CustomerIdentity | None` interface is the point — a real implementation
    can replace this body without changing the signature or any call site.
    """
    return None
