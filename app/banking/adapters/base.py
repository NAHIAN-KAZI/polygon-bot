from dataclasses import dataclass
from typing import Protocol

from app.banking.identity import CustomerIdentity


@dataclass(frozen=True)
class AdapterResult:
    data: dict


class AdapterUnavailableError(Exception):
    """Raised by an adapter on generic failure (timeout, non-auth HTTP error,
    network error, or a mock adapter's own simulated failure)."""


class AdapterAuthError(Exception):
    """Raised by an adapter when the downstream call is rejected for an auth
    reason (401/403), so callers can distinguish AUTH_REQUIRED from
    SERVICE_UNAVAILABLE per SRS FR-INTEG-06."""


class AdapterAccountSelectionRequiredError(Exception):
    """Raised when a real adapter needs an accountNumber it wasn't given, and the
    customer has 2+ accounts. Callers (chat.py) must surface
    ACCOUNT_SELECTION_REQUIRED instead of treating this as a generic failure."""

    def __init__(self, accounts: list[dict]):
        self.accounts = accounts
        super().__init__(f"account selection required among {len(accounts)} accounts")


class AdapterValidationError(Exception):
    """Raised for a structured, *expected* business-rule rejection -- a
    documented 400/410/429-class response (or a client-side precondition
    mirroring one, e.g. "provide exactly one of pin or password") -- that is
    neither an auth failure (AdapterAuthError) nor a generic service failure
    (AdapterUnavailableError). Added for T-57's OTP send/verify flow (ADR
    pending), where several distinct, documented rejection reasons need to
    reach the conversational layer distinguishably rather than collapsing
    into one generic error.

    `reason` is a small, stable, machine-readable code so callers can branch
    on it instead of string-matching `message` (the human-readable text,
    which may embed bank-provided detail such as remaining attempts).
    Current reasons in use (see app/banking/adapters/real.py for exactly
    which status code on which endpoint produces each):

      - "INVALID_PHONE"              -- otp/v1/send 400
      - "SEND_THROTTLED"             -- otp/v1/send 429 (cooldown or rate limit)
      - "SEND_UNAVAILABLE"           -- otp/v1/send 503 (SMS gateway down)
      - "OTP_INCORRECT"              -- otp/v1/verify 400 (wrong code)
      - "OTP_EXPIRED"                -- otp/v1/verify 410 (no OTP on record)
      - "OTP_BLOCKED"                -- otp/v1/verify 429 (3rd wrong attempt)
      - "PIN_OR_PASSWORD_REQUIRED"   -- freeze 400 (both or neither supplied)
      - "INVALID_CREDENTIALS"        -- freeze 401 "Invalid credentials"
            (wrong PIN/password -- verificationToken is NOT consumed, so it
            can be reused for a retry without resending OTP)
      - "INVALID_VERIFICATION_TOKEN" -- freeze 401 "Invalid or expired OTP
            verification" (token expired/used/wrong phone -- needs a fresh
            send+verify)

    `attempts_remaining` / `retry_after_seconds` are populated only where the
    specific case has a known value; both default to None otherwise rather
    than being guessed.
    """

    def __init__(
        self,
        reason: str,
        message: str,
        *,
        attempts_remaining: int | None = None,
        retry_after_seconds: int | None = None,
    ):
        self.reason = reason
        self.attempts_remaining = attempts_remaining
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class BankingAdapter(Protocol):
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        """Fulfill a banking subservice request. Raises AdapterUnavailableError
        or AdapterAuthError on failure."""
        ...
