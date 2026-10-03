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
    assert get_adapter_name("payments", "card_payment") == "mock"


def test_get_adapter_name_returns_mock_when_service_and_subservice_are_none_or_unrelated():
    assert get_adapter_name("payments", None) == "mock"
    assert get_adapter_name("payments", "mobile_recharge", "card_payment") == "mock"


def test_get_adapter_name_returns_real_for_each_synthetic_account_info_service():
    assert get_adapter_name("account_info", "balance") == "real:balance"
    assert get_adapter_name("account_info", "accounts") == "real:accounts"
    assert get_adapter_name("account_info", "device_history") == "real:device_history"
    assert get_adapter_name("account_info", "login_history") == "real:login_history"


def test_get_adapter_name_returns_real_for_beneficiary_service_id():
    # category is irrelevant to get_adapter_name's logic (it only branches on
    # service_id/subservice_id membership in REAL_ADAPTER_SUBSERVICE_IDS), so
    # any category string exercises the same branch.
    assert get_adapter_name("account_info", "beneficiary") == "real:beneficiary"


def test_get_adapter_name_returns_real_for_beneficiary_subservice_id():
    assert (
        get_adapter_name("payments", "some_other_service", "beneficiary")
        == "real:beneficiary"
    )


def test_get_adapter_name_returns_real_for_fee_quote_service_id():
    assert get_adapter_name("fees", "fee_quote") == "real:fee_quote"


def test_get_adapter_name_returns_real_for_fee_quote_subservice_id():
    assert (
        get_adapter_name("fees", "some_other_service", "fee_quote")
        == "real:fee_quote"
    )


# --- T-58: my_loans/fd_profit_history/dps_profit_history/disputes ----------
# --- independent coverage -- not touched by the implementing agent's own ---
# --- tests, which only asserted the adapter dict/REAL_ADAPTERS wiring in ---
# --- tests/test_real_adapters.py, not get_adapter_name's own routing. ------


def test_get_adapter_name_returns_real_for_my_loans_service_id():
    assert get_adapter_name("loan_services", "my_loans") == "real:my_loans"


def test_get_adapter_name_returns_real_for_fd_profit_history_service_id():
    assert get_adapter_name("account_info", "fd_profit_history") == "real:fd_profit_history"


def test_get_adapter_name_returns_real_for_dps_profit_history_service_id():
    assert get_adapter_name("account_info", "dps_profit_history") == "real:dps_profit_history"


def test_get_adapter_name_returns_real_for_disputes_service_id():
    assert get_adapter_name("service_requests", "disputes") == "real:disputes"


def test_get_adapter_name_returns_real_for_t58_subservice_ids():
    # subservice_id is checked before service_id (see
    # test_get_adapter_name_labels_matching_subservice_id_even_with_unrelated_service_id
    # above) -- confirm each of the 4 new ids is also recognized via that branch.
    assert get_adapter_name("x", "unrelated", "my_loans") == "real:my_loans"
    assert get_adapter_name("x", "unrelated", "fd_profit_history") == "real:fd_profit_history"
    assert get_adapter_name("x", "unrelated", "dps_profit_history") == "real:dps_profit_history"
    assert get_adapter_name("x", "unrelated", "disputes") == "real:disputes"


# --- T-57/T-60: cards, frezz_unfrezz (card freeze), beneficiary_add --------


def test_get_adapter_name_returns_real_for_cards_service_id():
    assert get_adapter_name("account_info", "cards") == "real:cards"


def test_get_adapter_name_returns_real_for_frezz_unfrezz_service_id():
    assert get_adapter_name("card_services", "frezz_unfrezz") == "real:frezz_unfrezz"


def test_get_adapter_name_returns_real_for_beneficiary_add_subservice_id():
    assert (
        get_adapter_name("polygon_services", "beneficiary", "beneficiary_add")
        == "real:beneficiary_add"
    )


def test_get_adapter_name_returns_real_for_beneficiary_add_service_id():
    assert get_adapter_name("beneficiary_management", "beneficiary_add") == "real:beneficiary_add"


def test_requires_identity_always_true():
    assert requires_identity("accounts", "transaction_history") is True
    assert requires_identity("payments", "mobile_recharge", "beneficiary") is True
    assert requires_identity("anything", None, None) is True
