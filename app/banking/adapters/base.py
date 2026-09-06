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
