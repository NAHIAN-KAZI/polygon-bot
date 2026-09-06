"""Tests for app/banking/adapters/base.py: the AdapterResult dataclass, the
adapter error types, and the BankingAdapter protocol shape.

BankingAdapter is a plain typing.Protocol (not @runtime_checkable), so it
cannot be used with isinstance(). Instead we verify a conforming class can
be constructed and its async fulfill() awaited successfully.
"""
import asyncio
import dataclasses

import pytest

from app.banking.adapters.base import (
    AdapterAccountSelectionRequiredError,
    AdapterAuthError,
    AdapterResult,
    AdapterUnavailableError,
    BankingAdapter,
)
from app.banking.identity import CustomerIdentity


def test_adapter_result_construction_and_field_access():
    result = AdapterResult(data={"balance": 100})
    assert result.data == {"balance": 100}


def test_adapter_result_is_frozen():
    result = AdapterResult(data={"balance": 100})
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.data = {"balance": 200}


def test_adapter_unavailable_error_is_exception_and_raisable():
    with pytest.raises(AdapterUnavailableError):
        raise AdapterUnavailableError("downstream timed out")
    assert issubclass(AdapterUnavailableError, Exception)


def test_adapter_auth_error_is_exception_and_raisable():
    with pytest.raises(AdapterAuthError):
        raise AdapterAuthError("401 from downstream")
    assert issubclass(AdapterAuthError, Exception)


def test_adapter_errors_are_distinct():
    assert not issubclass(AdapterUnavailableError, AdapterAuthError)
    assert not issubclass(AdapterAuthError, AdapterUnavailableError)

    with pytest.raises(AdapterAuthError):
        try:
            raise AdapterAuthError("401 from downstream")
        except AdapterUnavailableError:
            pytest.fail("AdapterAuthError should not be caught as AdapterUnavailableError")


def test_adapter_account_selection_required_error_is_exception_and_raisable():
    accounts = [{"accountNumber": "111"}]
    with pytest.raises(AdapterAccountSelectionRequiredError):
        raise AdapterAccountSelectionRequiredError(accounts)
    assert issubclass(AdapterAccountSelectionRequiredError, Exception)


def test_adapter_account_selection_required_error_sets_accounts_attribute():
    accounts = [
        {"accountNumber": "111", "accountName": "Savings"},
        {"accountNumber": "222", "accountName": "Checking"},
    ]

    exc = AdapterAccountSelectionRequiredError(accounts)

    assert exc.accounts == accounts
    assert exc.accounts is accounts


def test_adapter_account_selection_required_error_is_a_plain_sibling_not_a_subclass():
    exc = AdapterAccountSelectionRequiredError([{"accountNumber": "111"}])

    assert not isinstance(exc, AdapterUnavailableError)
    assert not isinstance(exc, AdapterAuthError)
    assert not issubclass(AdapterAccountSelectionRequiredError, AdapterUnavailableError)
    assert not issubclass(AdapterAccountSelectionRequiredError, AdapterAuthError)

    with pytest.raises(AdapterAccountSelectionRequiredError):
        try:
            raise AdapterAccountSelectionRequiredError([{"accountNumber": "111"}])
        except AdapterUnavailableError:
            pytest.fail(
                "AdapterAccountSelectionRequiredError should not be caught as AdapterUnavailableError"
            )


class _FakeAdapter:
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        return AdapterResult(data={"subservice": subservice, "customer_id": customer_identity.customer_id})


def test_fake_adapter_implements_banking_adapter_shape_and_fulfill_is_awaitable():
    adapter: BankingAdapter = _FakeAdapter()
    identity = CustomerIdentity(customer_id="cust-123")

    result = asyncio.run(adapter.fulfill(identity, "some.jwt.token", "balances", {"account": "checking"}))

    assert isinstance(result, AdapterResult)
    assert result.data == {"subservice": "balances", "customer_id": "cust-123"}
