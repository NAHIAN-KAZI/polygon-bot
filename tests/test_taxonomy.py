"""Tests for the live taxonomy fetcher in app/banking/taxonomy.py.

The HTTP layer is mocked by monkeypatching httpx.AsyncClient.get directly,
matching this codebase's existing style of monkeypatching external call
sites (see tests/test_documents_regression.py) rather than pulling in a new
test dependency like respx. No test hits the real platform API.

taxonomy.py keeps its cache/index as module-level globals, so a fixture
resets them before and after every test to avoid state leaking between
tests.
"""
import asyncio

import httpx
import pytest

import app.banking.taxonomy as taxonomy


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data


def _install_responses(monkeypatch, responses: dict[str, FakeResponse]):
    """responses maps an exact request path (e.g. "/support/v1/services") to
    a FakeResponse, or to an Exception instance to be raised instead."""

    async def fake_get(self, url, *args, **kwargs):
        for path, result in responses.items():
            if str(url).endswith(path):
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"unexpected URL requested: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


def _category(cat_id, active_service_id="svc", sub_ids=("sub",), is_active=True, service_active=True, sub_active_map=None):
    sub_active_map = sub_active_map or {sid: True for sid in sub_ids}
    return {
        "id": cat_id,
        "isActive": is_active,
        "services": [
            {
                "id": active_service_id,
                "isActive": service_active,
                "subServices": [
                    {"id": sid, "isActive": sub_active_map.get(sid, True)} for sid in sub_ids
                ],
            }
        ],
    }


SERVICES_PATH = "/support/v1/services"
PAY_TRANSFER_PATH = "/support/v1/pay-transfer"


def _ok(categories):
    return FakeResponse({"status": "success", "data": {"categories": categories}})


@pytest.fixture(autouse=True)
def reset_taxonomy_state():
    taxonomy._cache = None
    taxonomy._index = None
    yield
    taxonomy._cache = None
    taxonomy._index = None


def test_refresh_merges_both_endpoints_preserving_ids(monkeypatch):
    services_categories = [_category("banking", "accounts", ("checking", "savings"))]
    pay_transfer_categories = [_category("transfers", "wire", ("domestic",))]
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok(services_categories),
        PAY_TRANSFER_PATH: _ok(pay_transfer_categories),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    result = taxonomy.get_taxonomy()
    category_ids = {c["id"] for c in result["categories"]}
    # account_info, fees, service_requests, card_info, profile and
    # transfer_info are synthetic categories unconditionally appended by
    # _fetch_and_build() on every build, in addition to whatever the fetch
    # returns (T-19, T-41, T-58, T-64), so both fetched ids and the synthetic
    # ids must appear.
    assert category_ids == {
        "banking",
        "transfers",
        "account_info",
        "fees",
        "service_requests",
        "card_info",
        "profile",
        "transfer_info",
        "beneficiary_management",  # T-60 fix: beneficiary_add needs a real taxonomy home
        "card_requests", "support", "profile_update",  # T-75 customer-requested changes
        "app_actions",  # T-79: requests handed to the app (ui_actions.py)
    }

    banking = next(c for c in result["categories"] if c["id"] == "banking")
    assert banking["services"][0]["id"] == "accounts"
    sub_ids = {s["id"] for s in banking["services"][0]["subServices"]}
    assert sub_ids == {"checking", "savings"}

    assert taxonomy.is_valid_path("banking", "accounts", "checking")
    assert taxonomy.is_valid_path("transfers", "wire", "domestic")


def test_inactive_items_excluded_at_every_level(monkeypatch):
    categories = [
        {
            "id": "banking",
            "isActive": True,
            "services": [
                {
                    "id": "accounts",
                    "isActive": True,
                    "subServices": [
                        {"id": "checking", "isActive": True},
                        {"id": "old-sub", "isActive": False},
                    ],
                },
                {"id": "loans", "isActive": False, "subServices": []},
            ],
        },
        {"id": "archived", "isActive": False, "services": []},
    ]
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok(categories),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    result = taxonomy.get_taxonomy()
    category_ids = {c["id"] for c in result["categories"]}
    assert "archived" not in category_ids

    banking = next(c for c in result["categories"] if c["id"] == "banking")
    service_ids = {s["id"] for s in banking["services"]}
    assert service_ids == {"accounts"}
    accounts = banking["services"][0]
    sub_ids = {s["id"] for s in accounts["subServices"]}
    assert sub_ids == {"checking"}

    assert taxonomy.is_valid_path("banking", "accounts", "checking") is True
    assert taxonomy.is_valid_path("banking", "accounts", "old-sub") is False
    assert taxonomy.is_valid_path("banking", "loans") is False
    assert taxonomy.is_valid_path("archived", "anything") is False


def test_is_valid_path_true_and_false_cases(monkeypatch):
    services_categories = [_category("banking", "accounts", ("checking",))]
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok(services_categories),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.is_valid_path("banking", "accounts") is True
    assert taxonomy.is_valid_path("banking", "accounts", "checking") is True
    assert taxonomy.is_valid_path("nonexistent-category", "accounts") is False
    assert taxonomy.is_valid_path("banking", "nonexistent-service") is False
    assert taxonomy.is_valid_path("banking", "accounts", "nonexistent-sub") is False


def test_initialize_raises_when_first_fetch_fails_with_no_cache(monkeypatch):
    _install_responses(monkeypatch, {
        SERVICES_PATH: httpx.ConnectError("connection refused"),
        PAY_TRANSFER_PATH: _ok([]),
    })

    assert taxonomy._cache is None
    with pytest.raises(httpx.ConnectError):
        asyncio.run(taxonomy.initialize_taxonomy())
    assert taxonomy._cache is None


def test_refresh_failure_keeps_last_good_cache(monkeypatch):
    good_categories = [_category("banking", "accounts", ("checking",))]
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok(good_categories),
        PAY_TRANSFER_PATH: _ok([]),
    })
    asyncio.run(taxonomy.refresh_taxonomy())
    good_taxonomy = taxonomy.get_taxonomy()
    assert good_taxonomy["categories"]

    _install_responses(monkeypatch, {
        SERVICES_PATH: httpx.ConnectError("connection refused"),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.get_taxonomy() == good_taxonomy
    assert taxonomy.is_valid_path("banking", "accounts", "checking") is True


@pytest.mark.parametrize("malformed_body", [
    {"status": "success", "data": {}},
    {"status": "success", "data": {"categories": "not-a-list"}},
    {"status": "success"},
])
def test_malformed_response_shape_treated_as_fetch_failure(monkeypatch, malformed_body):
    good_categories = [_category("banking", "accounts", ("checking",))]
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok(good_categories),
        PAY_TRANSFER_PATH: _ok([]),
    })
    asyncio.run(taxonomy.refresh_taxonomy())
    good_taxonomy = taxonomy.get_taxonomy()

    _install_responses(monkeypatch, {
        SERVICES_PATH: FakeResponse(malformed_body),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.get_taxonomy() == good_taxonomy


def test_malformed_response_on_first_fetch_raises_not_unhandled_crash(monkeypatch):
    _install_responses(monkeypatch, {
        SERVICES_PATH: FakeResponse({"status": "success", "data": {"categories": "not-a-list"}}),
        PAY_TRANSFER_PATH: _ok([]),
    })

    with pytest.raises(ValueError):
        asyncio.run(taxonomy.initialize_taxonomy())
    assert taxonomy._cache is None


def test_synthetic_account_info_category_has_expected_services(monkeypatch):
    services_categories = [_category("banking", "accounts", ("checking",))]
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok(services_categories),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    result = taxonomy.get_taxonomy()
    account_info = next(c for c in result["categories"] if c["id"] == "account_info")
    service_ids = {s["id"] for s in account_info["services"]}
    assert service_ids == {
        "balance",
        "accounts",
        "device_history",
        "login_history",
        "fd_profit_history",
        "dps_profit_history",
        "cards",
        "account_transactions",
    }
    assert len(account_info["services"]) == 8


def test_synthetic_fees_category_has_expected_services(monkeypatch):
    services_categories = [_category("banking", "accounts", ("checking",))]
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok(services_categories),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    result = taxonomy.get_taxonomy()
    fees = next(c for c in result["categories"] if c["id"] == "fees")
    service_ids = {s["id"] for s in fees["services"]}
    assert service_ids == {"fee_quote"}
    assert len(fees["services"]) == 1


def test_synthetic_fees_path_is_valid(monkeypatch):
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.is_valid_path("fees", "fee_quote") is True


def test_synthetic_account_info_paths_are_valid(monkeypatch):
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.is_valid_path("account_info", "balance") is True
    assert taxonomy.is_valid_path("account_info", "accounts") is True
    assert taxonomy.is_valid_path("account_info", "device_history") is True
    assert taxonomy.is_valid_path("account_info", "login_history") is True


# --- T-57: `cards` synthetic service (account_info) -------------------------


def test_synthetic_account_info_cards_path_is_valid(monkeypatch):
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.is_valid_path("account_info", "cards") is True


def test_synthetic_account_info_rejects_unknown_service(monkeypatch):
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.is_valid_path("account_info", "nonexistent") is False


# --- T-58: service_requests synthetic category + fd/dps_profit_history ------
# --- independent coverage -- the implementing agent updated the merged-set --
# --- and account_info-services assertions above but added no dedicated ------
# --- per-category test for the new service_requests category (unlike the ---
# --- existing fees/account_info ones this mirrors), and no is_valid_path ----
# --- coverage at all for fd_profit_history/dps_profit_history/disputes. -----


def test_synthetic_service_requests_category_has_expected_services(monkeypatch):
    services_categories = [_category("banking", "accounts", ("checking",))]
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok(services_categories),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    result = taxonomy.get_taxonomy()
    service_requests = next(c for c in result["categories"] if c["id"] == "service_requests")
    service_ids = {s["id"] for s in service_requests["services"]}
    assert service_ids == {"disputes", "raise_dispute"}
    assert len(service_requests["services"]) == 2


def test_synthetic_service_requests_path_is_valid(monkeypatch):
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.is_valid_path("service_requests", "disputes") is True


def test_synthetic_service_requests_rejects_unknown_service(monkeypatch):
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.is_valid_path("service_requests", "nonexistent") is False


def test_synthetic_disputes_has_no_valid_subservices(monkeypatch):
    # Locks in the routing.py prompt note ("service_requests has exactly one
    # service, disputes, and it has no subservices at all -- never pass a
    # subservice argument"): disputes defines no subServices entry at all, so
    # is_valid_path must reject ANY subservice_id for it, not just a specific
    # made-up one.
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.is_valid_path("service_requests", "disputes", "anything") is False


def test_synthetic_fd_dps_profit_history_paths_are_valid(monkeypatch):
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.is_valid_path("account_info", "fd_profit_history") is True
    assert taxonomy.is_valid_path("account_info", "dps_profit_history") is True


def test_synthetic_account_info_rejects_fd_dps_profit_history_as_subservice_of_other_service(monkeypatch):
    # fd_profit_history/dps_profit_history are standalone services, not
    # subservices of anything else in account_info -- confirms they weren't
    # accidentally wired in as a subservice of e.g. "balance" instead.
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.is_valid_path("account_info", "balance", "fd_profit_history") is False
    assert taxonomy.is_valid_path("account_info", "balance", "dps_profit_history") is False


def test_synthetic_account_info_present_even_when_live_fetch_is_empty(monkeypatch):
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    result = taxonomy.get_taxonomy()
    category_ids = {c["id"] for c in result["categories"]}
    assert category_ids == {
        "account_info",
        "fees",
        "service_requests",
        "card_info",
        "profile",
        "transfer_info",
        "beneficiary_management",  # T-60 fix: beneficiary_add needs a real taxonomy home
        "card_requests", "support", "profile_update",  # T-75 customer-requested changes
        "app_actions",  # T-79: requests handed to the app (ui_actions.py)
    }


# --- T-64: 16 read-only synthetic services (ADR-0011 Amendment 2026-10-03) --

_T64_PATHS = [
    ("account_info", "account_transactions"),
    ("card_info", "card_limit_requests"),
    ("card_info", "card_products"),
    ("card_info", "virtual_card_requests"),
    ("card_info", "replacement_requests"),
    ("card_info", "credit_card_summary"),
    ("card_info", "credit_card_statement"),
    ("profile", "profile"),
    ("profile", "address"),
    ("profile", "contacts"),
    ("profile", "profile_change_requests"),
    ("profile", "contact_priority_requests"),
    ("transfer_info", "gifts_received"),
    ("transfer_info", "email_transfers"),
    ("transfer_info", "qr_payment_history"),
    ("transfer_info", "transfer_limit"),
]


def test_t64_path_list_covers_exactly_17_services():
    assert len(_T64_PATHS) == 16
    assert len(set(_T64_PATHS)) == 16


@pytest.mark.parametrize("category_id,service_id", _T64_PATHS)
def test_synthetic_t64_paths_are_valid(monkeypatch, category_id, service_id):
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    assert taxonomy.is_valid_path(category_id, service_id) is True
    # None of the T-64 services define subservices.
    assert taxonomy.is_valid_path(category_id, service_id, "anything") is False


@pytest.mark.parametrize(
    "category_id,expected",
    [
        (
            "card_info",
            {
                "card_limit_requests",
                "card_products",
                "virtual_card_requests",
                "replacement_requests",
                "credit_card_summary",
                "credit_card_statement",
            },
        ),
        (
            "profile",
            {
                "profile",
                "address",
                "contacts",
                "profile_change_requests",
                "contact_priority_requests",
            },
        ),
        (
            "transfer_info",
            {"gifts_received", "email_transfers", "qr_payment_history", "transfer_limit"},
        ),
    ],
)
def test_synthetic_t64_new_categories_have_expected_services(monkeypatch, category_id, expected):
    _install_responses(monkeypatch, {
        SERVICES_PATH: _ok([]),
        PAY_TRANSFER_PATH: _ok([]),
    })

    asyncio.run(taxonomy.refresh_taxonomy())

    category = next(c for c in taxonomy.get_taxonomy()["categories"] if c["id"] == category_id)
    service_ids = [s["id"] for s in category["services"]]
    assert set(service_ids) == expected
    assert len(service_ids) == len(expected)
