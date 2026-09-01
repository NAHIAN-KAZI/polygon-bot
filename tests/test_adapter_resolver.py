"""Tests for app/banking/adapters/__init__.py: get_adapter() name resolution
and fulfill_banking_service() end-to-end wiring (adapter_map -> get_adapter ->
adapter.fulfill).

No real network calls are made -- adapter_map.get_adapter_name and/or the
resolved adapter's fulfill() are monkeypatched directly, matching this
repo's existing style (tests/test_real_adapters.py, tests/test_routing.py).

fulfill_banking_service() is async; driven via asyncio.run() inside sync
test functions, matching tests/test_adapter_base.py (no pytest-asyncio in
this repo).
"""
import asyncio

import pytest

from app.banking import adapter_map
from app.banking.adapters import fulfill_banking_service, get_adapter
from app.banking.adapters.base import AdapterAuthError, AdapterResult
from app.banking.adapters.mock import mock_adapter
from app.banking.adapters.real import REAL_ADAPTERS
from app.banking.identity import CustomerIdentity

_IDENTITY = CustomerIdentity(customer_id="cust-123")
_JWT = "test.jwt.token"


# --- get_adapter -------------------------------------------------------------


def test_get_adapter_mock_returns_mock_adapter_singleton():
    assert get_adapter("mock") is mock_adapter


def test_get_adapter_real_balance_returns_correct_singleton():
    assert get_adapter("real:balance") is REAL_ADAPTERS["real:balance"]


def test_get_adapter_real_transaction_history_returns_correct_singleton():
    assert get_adapter("real:transaction_history") is REAL_ADAPTERS["real:transaction_history"]


def test_get_adapter_unknown_name_raises_value_error():
    with pytest.raises(ValueError, match="nonexistent-name"):
        get_adapter("nonexistent-name")


# --- fulfill_banking_service --------------------------------------------------


def test_fulfill_banking_service_routes_to_mock_adapter(monkeypatch):
    monkeypatch.setattr(adapter_map, "get_adapter_name", lambda *a, **k: "mock")

    result = asyncio.run(
        fulfill_banking_service(
            _IDENTITY, _JWT, "payments", "mobile_recharge", None, {"amount": 10}
        )
    )

    assert isinstance(result, AdapterResult)
    assert result.data["mock"] is True


def test_fulfill_banking_service_propagates_real_adapter_exception_uncaught(monkeypatch):
    monkeypatch.setattr(adapter_map, "get_adapter_name", lambda *a, **k: "real:balance")

    async def fake_fulfill(self, customer_identity, jwt, subservice, payload):
        raise AdapterAuthError("jwt rejected")

    monkeypatch.setattr(type(REAL_ADAPTERS["real:balance"]), "fulfill", fake_fulfill)

    with pytest.raises(AdapterAuthError):
        asyncio.run(
            fulfill_banking_service(
                _IDENTITY, _JWT, "banking", "accounts", "balance", {"accountNumber": "111"}
            )
        )


class _RecordingAdapter:
    def __init__(self):
        self.calls = []

    async def fulfill(self, customer_identity, jwt, subservice, payload):
        self.calls.append(
            {
                "customer_identity": customer_identity,
                "jwt": jwt,
                "subservice": subservice,
                "payload": payload,
            }
        )
        return AdapterResult(data={})


def test_fulfill_banking_service_passes_service_when_subservice_is_none(monkeypatch):
    recording_adapter = _RecordingAdapter()
    monkeypatch.setattr(adapter_map, "get_adapter_name", lambda *a, **k: "recording")
    monkeypatch.setitem(REAL_ADAPTERS, "recording", recording_adapter)

    asyncio.run(
        fulfill_banking_service(_IDENTITY, _JWT, "banking", "accounts", None, {"id": "acc-1"})
    )

    assert len(recording_adapter.calls) == 1
    assert recording_adapter.calls[0]["subservice"] == "accounts"


def test_fulfill_banking_service_passes_subservice_when_present(monkeypatch):
    recording_adapter = _RecordingAdapter()
    monkeypatch.setattr(adapter_map, "get_adapter_name", lambda *a, **k: "recording")
    monkeypatch.setitem(REAL_ADAPTERS, "recording", recording_adapter)

    asyncio.run(
        fulfill_banking_service(
            _IDENTITY, _JWT, "banking", "accounts", "some-subservice", {"id": "acc-1"}
        )
    )

    assert len(recording_adapter.calls) == 1
    assert recording_adapter.calls[0]["subservice"] == "some-subservice"
