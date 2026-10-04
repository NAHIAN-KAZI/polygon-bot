REAL_ADAPTER_SUBSERVICE_IDS = {
    "transaction_history",
    "balance",
    "accounts",
    "device_history",
    "login_history",
    "beneficiary",
    "fee_quote",
    "my_loans",
    "fd_profit_history",
    "dps_profit_history",
    "disputes",
    "cards",
    # T-57: *** MUTATING exception *** -- live, navigable real service id
    # (category "card_services"), not a synthetic taxonomy addition. See
    # FreezeCardAdapter's docstring in app/banking/adapters/real.py.
    "frezz_unfrezz",
    # T-60: *** MUTATING exception *** -- distinct id from "beneficiary"
    # (which stays the existing list operation). See BeneficiaryAddAdapter's
    # docstring in app/banking/adapters/real.py.
    "beneficiary_add",
    # T-64: read-only (GET) real adapters -- see app/banking/adapters/real.py.
    "my_tickets",
    "account_transactions",
    "card_limit_requests",
    "card_products",
    "virtual_card_requests",
    "replacement_requests",
    "credit_card_summary",
    "credit_card_statement",
    "profile",
    "address",
    "contacts",
    "profile_change_requests",
    "contact_priority_requests",
    "gifts_received",
    "email_transfers",
    "qr_payment_history",
    "transfer_limit",
    # T-75: *** MUTATING, user-approved 2026-10-04 *** -- complaint, nickname and
    # address act only after an explicit yes; email and mobile only after a
    # verified OTP. See the adapters' docstrings in app/banking/adapters/real.py.
    "submit_complaint",
    "update_nickname",
    "update_address",
    "update_email",
    "update_mobile",
}


def get_adapter_name(category_id: str, service_id: str, subservice_id: str | None = None) -> str:
    if subservice_id in REAL_ADAPTER_SUBSERVICE_IDS:
        return f"real:{subservice_id}"
    if service_id in REAL_ADAPTER_SUBSERVICE_IDS:
        return f"real:{service_id}"
    return "mock"


def requires_identity(category_id: str, service_id: str, subservice_id: str | None = None) -> bool:
    return True
