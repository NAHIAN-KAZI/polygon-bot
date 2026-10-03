import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_cache: dict | None = None
_index: dict | None = None

# ADR-0011 Amendment 2026-09-01 (T-19): these 4 are always-available account
# features the mobile app calls directly, never surfaced via the navigation
# grid, so they can never appear in a live fetch. Closed, named exception —
# see banking-service-catalog agent file before adding another id here.
# Extended by Amendment 2026-09-29 (T-41, `fees`/`fee_quote`), Amendment
# 2026-10-01 (T-58, `account_info`/`fd_profit_history`+`dps_profit_history`
# and the new `service_requests`/`disputes` category), Amendment 2026-10-01
# (T-57, `account_info`/`cards`), and Amendment 2026-10-01 (T-61,
# `service_requests`/`raise_dispute`) — each a standalone utility endpoint (or,
# for `raise_dispute`, a gather+redirect-only flow with no real submission
# endpoint at all) the app/chatbot calls directly, never surfaced via the
# navigation grid, so none of them can ever appear in a live fetch either.
_SYNTHETIC_CATEGORIES = [
    {
        "id": "account_info",
        "name": "Account Information",
        "isActive": True,
        "services": [
            {"id": "balance", "name": "Balance", "isActive": True},
            {"id": "accounts", "name": "My Accounts", "isActive": True},
            {"id": "device_history", "name": "Device History", "isActive": True},
            {"id": "login_history", "name": "Login History", "isActive": True},
            {"id": "fd_profit_history", "name": "FD Profit History", "isActive": True},
            {"id": "dps_profit_history", "name": "DPS Profit History", "isActive": True},
            {"id": "cards", "name": "My Cards", "isActive": True},
            # ADR-0011 Amendment 2026-10-03 (T-64).
            {"id": "account_transactions", "name": "Account Transactions", "isActive": True},
        ],
    },
    # ADR-0011 Amendment 2026-09-29 (T-41): fee-quote is a standalone utility
    # endpoint the app calls directly for a fee preview, never surfaced via the
    # navigation grid, so it can never appear in a live fetch either.
    {
        "id": "fees",
        "name": "Fees",
        "isActive": True,
        "services": [
            {"id": "fee_quote", "name": "Fee Quote", "isActive": True},
        ],
    },
    # ADR-0011 Amendment 2026-10-01 (T-58): disputes list is a standalone
    # service-request endpoint shared by ATM_SUPPORT/CARD_ISSUE/FAILED_TRANSFER,
    # never surfaced via the navigation grid, so it can never appear in a live
    # fetch either. Extended by Amendment 2026-10-01 (T-61, `raise_dispute`) —
    # gather+redirect only, never submits a real dispute.
    {
        "id": "service_requests",
        "name": "Service Requests",
        "isActive": True,
        "services": [
            {"id": "disputes", "name": "Disputes", "isActive": True},
            {"id": "raise_dispute", "name": "Raise Dispute", "isActive": True},
        ],
    },
    # ADR-0011 Amendment 2026-10-03 (T-64): read-only (GET) card, profile and
    # transfer-history endpoints the app calls directly, never surfaced via the
    # navigation grid, so they can never appear in a live fetch either.
    {
        "id": "card_info",
        "name": "Card Information",
        "isActive": True,
        "services": [
            {"id": "card_limit_requests", "name": "Card Limit Requests", "isActive": True},
            {"id": "card_products", "name": "Card Products", "isActive": True},
            {"id": "virtual_card_requests", "name": "Virtual Card Requests", "isActive": True},
            {"id": "replacement_requests", "name": "Card Replacement Requests", "isActive": True},
            {"id": "credit_card_summary", "name": "Credit Card Summary", "isActive": True},
            {"id": "credit_card_statement", "name": "Credit Card Statement", "isActive": True},
        ],
    },
    {
        "id": "profile",
        "name": "Profile",
        "isActive": True,
        "services": [
            {"id": "profile", "name": "My Profile", "isActive": True},
            {"id": "address", "name": "Address", "isActive": True},
            {"id": "contacts", "name": "Contacts", "isActive": True},
            {"id": "profile_change_requests", "name": "Profile Change Requests", "isActive": True},
            {"id": "contact_priority_requests", "name": "Contact Priority Requests", "isActive": True},
        ],
    },
    {
        "id": "transfer_info",
        "name": "Transfer Information",
        "isActive": True,
        "services": [
            {"id": "gifts_received", "name": "Gifts Received", "isActive": True},
            {"id": "email_transfers", "name": "Email Transfers", "isActive": True},
            {"id": "qr_payment_history", "name": "QR Payment History", "isActive": True},
            {"id": "transfer_limit", "name": "Transfer Limit", "isActive": True},
        ],
    },
    # ADR-0011 Amendment 2026-10-03 (T-60 fix): adding a beneficiary has no live
    # catalog entry (the live polygon_services/beneficiary is the send/list one).
    {
        "id": "beneficiary_management",
        "name": "Beneficiary Management",
        "isActive": True,
        "services": [
            {"id": "beneficiary_add", "name": "Add Beneficiary", "isActive": True},
        ],
    },
]


async def _fetch_json(client: httpx.AsyncClient, path: str) -> dict:
    resp = await client.get(f"{settings.PLATFORM_API_BASE_URL}{path}")
    resp.raise_for_status()
    body = resp.json()
    categories = body["data"]["categories"]
    if not isinstance(categories, list):
        raise ValueError(f"unexpected categories shape from {path}")
    return categories


async def _fetch_merged_categories() -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        services_categories = await _fetch_json(client, "/support/v1/services")
        pay_transfer_categories = await _fetch_json(client, "/support/v1/pay-transfer")
    return services_categories + pay_transfer_categories


def _filter_active(categories: list[dict]) -> list[dict]:
    active_categories = []
    for category in categories:
        if not category.get("isActive", True):
            continue
        active_services = []
        for service in category.get("services", []):
            if not service.get("isActive", True):
                continue
            if "subServices" in service:
                service = {
                    **service,
                    "subServices": [
                        sub for sub in service["subServices"] if sub.get("isActive", True)
                    ],
                }
            active_services.append(service)
        active_categories.append({**category, "services": active_services})
    return active_categories


def _build_index(categories: list[dict]) -> dict:
    index: dict[str, dict[str, set[str]]] = {}
    for category in categories:
        service_map = index.setdefault(category["id"], {})
        for service in category["services"]:
            sub_ids = {sub["id"] for sub in service.get("subServices", [])}
            service_map[service["id"]] = sub_ids
    return index


async def _fetch_and_build() -> tuple[dict, dict]:
    raw_categories = await _fetch_merged_categories()
    active_categories = _filter_active(raw_categories) + _SYNTHETIC_CATEGORIES
    taxonomy = {"categories": active_categories}
    index = _build_index(active_categories)
    return taxonomy, index


async def refresh_taxonomy() -> None:
    """Refresh the cached taxonomy. On failure, logs and keeps serving the last good cache."""
    global _cache, _index
    try:
        taxonomy, index = await _fetch_and_build()
    except Exception:
        logger.exception("Taxonomy refresh failed; continuing to serve cached taxonomy")
        return
    _cache = taxonomy
    _index = index


async def _refresh_loop() -> None:
    while True:
        await asyncio.sleep(settings.TAXONOMY_REFRESH_SECONDS)
        await refresh_taxonomy()


async def initialize_taxonomy() -> None:
    """Fetch the taxonomy once at startup (raising if there's no cache to fall back on),
    then schedule the periodic background refresh."""
    global _cache, _index
    if _cache is None:
        taxonomy, index = await _fetch_and_build()
        _cache = taxonomy
        _index = index
    asyncio.create_task(_refresh_loop())


def get_taxonomy() -> dict:
    return _cache if _cache is not None else {"categories": []}


def is_valid_path(category_id: str, service_id: str, subservice_id: str | None = None) -> bool:
    if _index is None:
        return False
    service_map = _index.get(category_id)
    if service_map is None or service_id not in service_map:
        return False
    if subservice_id is None:
        return True
    return subservice_id in service_map[service_id]
