"""Tests for app/banking/adapters/mock.py: MockAdapter always succeeds and
echoes back placeholder data for any subservice/payload.

fulfill() is async; following tests/test_adapter_base.py's pattern, we drive
it with asyncio.run() inside sync test functions rather than adding
pytest-asyncio as a dependency.
"""
import asyncio

from app.banking.adapters.base import AdapterResult
from app.banking.adapters.mock import mock_adapter
from app.banking.identity import CustomerIdentity

_IDENTITY = CustomerIdentity(customer_id="cust-123")


def test_fulfill_returns_adapter_result_with_mock_flag():
    result = asyncio.run(mock_adapter.fulfill(_IDENTITY, "some.jwt.token", "balances", {"account": "checking"}))

    assert isinstance(result, AdapterResult)
    assert result.data["mock"] is True


def test_fulfill_echoes_subservice():
    result = asyncio.run(mock_adapter.fulfill(_IDENTITY, None, "mobile_recharge", {}))

    assert result.data["subservice"] == "mobile_recharge"


def test_fulfill_echoes_payload_dict():
    payload = {"account": "checking", "amount": 100}
    result = asyncio.run(mock_adapter.fulfill(_IDENTITY, "jwt", "beneficiary", payload))

    assert result.data["payload_echo"] == payload


def test_fulfill_echoes_none_payload_without_error():
    result = asyncio.run(mock_adapter.fulfill(_IDENTITY, "jwt", "beneficiary", None))

    assert result.data["payload_echo"] is None


def test_fulfill_never_raises_for_edge_case_inputs():
    minimal_identity = CustomerIdentity(customer_id="")

    for jwt, payload in [
        (None, {}),
        ("jwt", {"nested": {"a": [1, 2, 3]}}),
        (None, None),
    ]:
        result = asyncio.run(mock_adapter.fulfill(minimal_identity, jwt, "transaction_history", payload))
        assert isinstance(result, AdapterResult)
        assert result.data["payload_echo"] == payload


def test_fulfill_message_is_nonempty_and_mentions_subservice():
    result = asyncio.run(mock_adapter.fulfill(_IDENTITY, "jwt", "mobile_recharge", None))

    message = result.data["message"]
    assert isinstance(message, str)
    assert len(message) > 0
    assert "mobile_recharge" in message
