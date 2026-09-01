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
    assert category_ids == {"banking", "transfers"}

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
