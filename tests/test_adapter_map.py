"""Tests for app/banking/adapter_map.py: routing category/service/subservice
ids to a real or mock adapter name, and the identity-requirement gate."""
from app.banking.adapter_map import get_adapter_name, requires_identity


def test_get_adapter_name_returns_real_for_service_id_match():
    assert get_adapter_name("accounts", "transaction_history") == "real:transaction_history"


def test_get_adapter_name_returns_real_for_subservice_id_match():
    # subservice_id is checked before service_id unconditionally, so this
    # matches on the `subservice_id in REAL_ADAPTER_SUBSERVICE_IDS` branch.
    assert (
        get_adapter_name("accounts", None, "transaction_history")
        == "real:transaction_history"
    )


def test_get_adapter_name_labels_matching_subservice_id_even_with_unrelated_service_id():
    # Regression test: subservice_id must be checked before service_id even
    # when service_id is truthy but unrelated, so the label names whichever
    # id actually matched rather than always preferring service_id.
    assert (
        get_adapter_name("accounts", "some_other_service", "transaction_history")
        == "real:transaction_history"
    )


def test_get_adapter_name_returns_mock_for_unrelated_service_id():
    assert get_adapter_name("payments", "mobile_recharge") == "mock"
    assert get_adapter_name("payments", "beneficiary") == "mock"


def test_get_adapter_name_returns_mock_when_service_and_subservice_are_none_or_unrelated():
    assert get_adapter_name("payments", None) == "mock"
    assert get_adapter_name("payments", "mobile_recharge", "beneficiary") == "mock"


def test_get_adapter_name_returns_real_for_each_synthetic_account_info_service():
    assert get_adapter_name("account_info", "balance") == "real:balance"
    assert get_adapter_name("account_info", "accounts") == "real:accounts"
    assert get_adapter_name("account_info", "device_history") == "real:device_history"
    assert get_adapter_name("account_info", "login_history") == "real:login_history"


def test_requires_identity_always_true():
    assert requires_identity("accounts", "transaction_history") is True
    assert requires_identity("payments", "mobile_recharge", "beneficiary") is True
    assert requires_identity("anything", None, None) is True
